"""
Aislamiento entre contenedores.

Es la garantía que sostiene el producto: los datos de un cliente no se ven, no se
tocan y no se cuentan desde otro. Acá se prueban las cuatro capas que la producen,
porque cada una falla distinto:

1. **El schema** — `django-tenants` pone cada contenedor en su propio schema de
   PostgreSQL. Si esto se rompe, se rompe todo lo demás.
2. **El header `X-Tenant`** — `TenantHeaderMiddleware` resuelve el schema. Sin
   header se opera en el público, y las rutas de tenant ni siquiera existen ahí.
3. **La membresía** — `EsMiembroDelTenant` exige una fila en `SegUsuarioCliente`.
   Es lo único que impide que un usuario legítimo de A mande `X-Tenant: b`.
4. **Los permisos** — `UserTenantPermissions` vive *dentro* de cada schema, así
   que los grupos que autorizan en A no autorizan en B, ni siquiera al mismo
   usuario.

Se montan dos contenedores reales (`aislamiento_a` y `aislamiento_b`), con schemas
y migraciones de verdad. Eso cuesta unos 25 s, y por eso se crean una sola vez para
todo el módulo en `setUpModule` en vez de una vez por clase: los `TestCase` de abajo
revierten sus propias escrituras en cada test, así que el escenario se puede
compartir sin que un test contamine al siguiente.

Correr solo esto:

    python manage.py test contenedor.tests_aislamiento
"""

from datetime import timedelta

import importlib

from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase
from django.urls import Resolver404, resolve
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework_simplejwt.tokens import RefreshToken
from tenant_users.permissions.models import UserTenantPermissions

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo
from general.models import GenItem
from seguridad.models import SegUsuario, SegUsuarioCliente

ESQUEMA_A = 'aislamiento_a'
ESQUEMA_B = 'aislamiento_b'

RUTA_ITEM = '/general/item/'
RUTA_ME = '/seguridad/me/'
# `GenDocumentoViewSet` se queda con las permission_classes por defecto
# (`EsMiembroDelTenant` + `SuscripcionVigente`), sin permiso de modelo encima. Es la
# ruta con la que se prueba la membresía: acá un 403 solo puede venir de ella.
#
# `GenItemViewSet`, en cambio, declara `TienePermisoModelo`, así que un 403 suyo
# puede venir de la membresía o de los permisos. Confundir las dos cosas deja pasar
# mutaciones: con `EsMiembroDelTenant` desactivado, un extraño sigue recibiendo 403
# en `/general/item/` porque tampoco tiene permisos de modelo en ese contenedor.
RUTA_DOCUMENTO = '/general/documento/'

# Dónde monta `torioapp/urls_tenant.py` el router de cada app de tenant. Si se agrega
# una app al urlconf hay que agregarla acá, o sus endpoints quedan fuera del barrido;
# `test_el_barrido_cubre_todos_los_viewsets` es lo que hace ruidoso ese olvido.
MONTAJES = [
    ('general', 'general.urls'),
    ('contabilidad', 'contabilidad.urls'),
    ('turno', 'turno.urls'),
    ('humano', 'humano.urls'),
    ('inventario', 'inventario.urls'),
    ('seguridad', 'seguridad.urls_tenant'),
]

# Id que no existe en ningún contenedor. Sirve para las rutas de detalle: los permisos
# corren en `initial()`, antes de que la vista busque el objeto, así que un no-miembro
# recibe 403 sin que el id llegue a consultarse.
_PK_INEXISTENTE = 999999


def _ruta_del_viewset(montaje, prefijo, viewset):
    """
    Una URL real por viewset, verificada contra el resolver.

    No se usa `reverse()` a propósito: `periodo` y `programacion` están registrados con
    el mismo basename en dos apps distintas, y `reverse` devolvería la misma URL para
    los dos, dejando dos viewsets sin probar mientras el conteo se ve completo. Acá se
    arma el path y se confirma con `resolve()` que apunta al viewset esperado.

    Se prefiere la ruta de listado; si el viewset no la tiene (varios son solo
    `seleccionar`), se cae a sus acciones y por último a la ruta de detalle.
    """
    candidatos = [f'/{montaje}/{prefijo}/']
    acciones = [
        getattr(viewset, nombre) for nombre in dir(viewset)
        if getattr(getattr(viewset, nombre, None), 'mapping', None)
    ]
    candidatos += [
        f'/{montaje}/{prefijo}/{a.url_path}/' for a in acciones if not a.detail
    ]
    candidatos.append(f'/{montaje}/{prefijo}/{_PK_INEXISTENTE}/')
    candidatos += [
        f'/{montaje}/{prefijo}/{_PK_INEXISTENTE}/{a.url_path}/' for a in acciones if a.detail
    ]

    for url in candidatos:
        try:
            encontrado = resolve(url, urlconf='torioapp.urls_tenant')
        except Resolver404:
            continue
        if getattr(encontrado.func, 'cls', None) is viewset:
            return url
    return None


def rutas_de_tenant():
    """[(etiqueta, url)] con una ruta por viewset servido dentro de un contenedor."""
    rutas = []
    for montaje, modulo in MONTAJES:
        for prefijo, viewset, _ in importlib.import_module(modulo).router.registry:
            rutas.append((f'{montaje}/{prefijo}', _ruta_del_viewset(montaje, prefijo, viewset)))
    return rutas


# El de `EsMiembroDelTenant`. Se afirma explícitamente para que el test siga
# apuntando a la membresía si mañana alguien le pone permisos de modelo a la vista.
MENSAJE_NO_MIEMBRO = 'No tienes acceso a este contenedor.'


class Escenario:
    """
    Dos contenedores y cinco usuarios, compartidos por todo el módulo.

    Los usuarios cubren las combinaciones que importan:

    | Usuario    | Miembro de | Permisos de modelo             |
    |------------|------------|--------------------------------|
    | `sol_a`    | A          | item, en A                     |
    | `sol_b`    | B          | item, en B                     |
    | `ambos`    | A y B      | item, solo en A                |
    | `ajeno`    | ninguno    | —                              |
    | `fantasma` | ninguno    | **todos**, en B                |

    `ambos` es el caso interesante para las fugas: como es miembro legítimo de los dos,
    cualquier mezcla se le manifiesta sin necesidad de forjar nada.

    `fantasma` es el que hace medible el barrido de endpoints. Tiene fila de
    `UserTenantPermissions` en B con todos los permisos de modelo, pero **no** tiene
    `SegUsuarioCliente`: es el estado que quedaría si una baja de membresía fallara a
    medias. Sin él, un 403 en los 94 endpoints no probaría nada, porque los que exigen
    permiso de modelo rechazarían igual a cualquier extraño y el barrido pasaría aunque
    la membresía estuviera desactivada — el mismo falso positivo que ya nos mordió en
    `MembresiaTests`. Con él, el único motivo posible de 403 es `EsMiembroDelTenant`.
    """

    cliente_a = None
    cliente_b = None
    sol_a = None
    sol_b = None
    ambos = None
    ajeno = None
    fantasma = None


def _crear_contenedor(schema, nombre, dominio):
    """Crea el tenant con su schema real, su dominio y una suscripción vigente."""
    cliente = CtnCliente(
        schema_name=schema,
        nombre=nombre,
        telefono='3000000000',
        correo=f'{schema}@ejemplo.com',
    )
    # `auto_create_schema` crea el schema y le corre las migraciones de TENANT_APPS.
    cliente.save(verbosity=0)
    CtnDominio.objects.create(tenant=cliente, domain=dominio, is_primary=True)
    return cliente


def _suscribir(cliente, usuario, tipo, dias=30):
    """
    Deja el contenedor con suscripción vigente.

    Sin esto `SuscripcionVigente` responde 403 a todo y los tests de aislamiento
    no llegarían a ejercitar lo que quieren probar.
    """
    hoy = timezone.localdate()
    suscripcion = CtnSuscripcion.objects.create(
        cliente=cliente,
        usuario=usuario,
        suscripcion_tipo=tipo,
        fecha_inicio=hoy - timedelta(days=1),
        fecha_fin=hoy + timedelta(days=dias),
        frecuencia=CtnSuscripcion.FRECUENCIA_PRUEBA,
    )
    CtnCliente.objects.filter(pk=cliente.pk).update(suscripcion=suscripcion)
    cliente.refresh_from_db()
    return suscripcion


def _grupo_items(nombre):
    """Grupo con los cuatro permisos de `GenItem`, el modelo que usan los tests."""
    grupo = Group.objects.create(name=nombre)
    grupo.permissions.set(
        Permission.objects.filter(
            content_type__app_label='general',
            content_type__model='genitem',
        )
    )
    return grupo


def setUpModule():
    from general.signals import limpiar_caches

    # Las cachés de auditoría van por schema, y estos schemas nacen y mueren dentro
    # del mismo proceso: una entrada vieja sobreviviría al schema que la originó.
    limpiar_caches()

    with schema_context(get_public_schema_name()):
        Escenario.sol_a = SegUsuario.objects.create(
            email='sol.a@ejemplo.com', is_active=True, is_verified=True,
        )
        Escenario.sol_b = SegUsuario.objects.create(
            email='sol.b@ejemplo.com', is_active=True, is_verified=True,
        )
        Escenario.ambos = SegUsuario.objects.create(
            email='ambos@ejemplo.com', is_active=True, is_verified=True,
        )
        Escenario.ajeno = SegUsuario.objects.create(
            email='ajeno@ejemplo.com', is_active=True, is_verified=True,
        )
        Escenario.fantasma = SegUsuario.objects.create(
            email='fantasma@ejemplo.com', is_active=True, is_verified=True,
        )

        tipo = CtnSuscripcionTipo.objects.create(
            id=98, nombre='Aislamiento', precio=0, suscripcion_categoria_id=98,
        )

        Escenario.cliente_a = _crear_contenedor(ESQUEMA_A, 'Contenedor A', 'a.aislamiento.test')
        Escenario.cliente_b = _crear_contenedor(ESQUEMA_B, 'Contenedor B', 'b.aislamiento.test')

        _suscribir(Escenario.cliente_a, Escenario.sol_a, tipo)
        _suscribir(Escenario.cliente_b, Escenario.sol_b, tipo)

        grupo_a = _grupo_items('items_a')
        grupo_b = _grupo_items('items_b')

        Escenario.cliente_a.add_user(Escenario.sol_a, grupos=[grupo_a], propietario=True)
        Escenario.cliente_b.add_user(Escenario.sol_b, grupos=[grupo_b], propietario=True)
        # Miembro de los dos, pero con permisos de item solo en A: si los grupos se
        # filtraran de un schema al otro, este usuario podría escribir en B.
        Escenario.cliente_a.add_user(Escenario.ambos, grupos=[grupo_a])
        Escenario.cliente_b.add_user(Escenario.ambos)

        # `fantasma`: permisos de modelo en B sin membresía en B. No se usa `add_user`
        # justamente porque ese método escribe las dos filas; acá hace falta solo una.
        grupo_todo = Group.objects.create(name='todos_los_permisos')
        grupo_todo.permissions.set(Permission.objects.all())
        with schema_context(ESQUEMA_B):
            permisos = UserTenantPermissions.objects.create(profile=Escenario.fantasma)
            permisos.groups.set([grupo_todo])


def tearDownModule():
    from general.signals import limpiar_caches

    with schema_context(get_public_schema_name()):
        for cliente in (Escenario.cliente_a, Escenario.cliente_b):
            if cliente is not None:
                CtnDominio.objects.filter(tenant=cliente).delete()
                cliente.delete(force_drop=True)
    limpiar_caches()


class AislamientoBase(TestCase):
    """
    Base con los ayudantes de petición.

    El `set_schema_to_public` de limpieza no es cosmético: el middleware deja la
    conexión apuntando al último tenant resuelto, y sin restaurarla el test
    siguiente empezaría dentro del schema del anterior.
    """

    def setUp(self):
        self.addCleanup(connection.set_schema_to_public)

    @staticmethod
    def _token(usuario):
        return str(RefreshToken.for_user(usuario).access_token)

    def _get(self, ruta, usuario=None, tenant=None, **kwargs):
        return self.client.get(ruta, **self._headers(usuario, tenant), **kwargs)

    def _post(self, ruta, datos, usuario=None, tenant=None):
        return self.client.post(
            ruta, datos, content_type='application/json', **self._headers(usuario, tenant),
        )

    def _headers(self, usuario, tenant):
        cabeceras = {}
        if usuario is not None:
            cabeceras['authorization'] = f'Bearer {self._token(usuario)}'
        if tenant is not None:
            cabeceras['x-tenant'] = tenant
        return {'headers': cabeceras}

    @staticmethod
    def _crear_item(schema, nombre):
        with schema_context(schema):
            return GenItem.objects.create(nombre=nombre)


# --------------------------------------------------------------------------- #
# 1. El schema
# --------------------------------------------------------------------------- #

class DatosPorSchemaTests(AislamientoBase):
    """Lo que se escribe en un contenedor no existe en el otro."""

    def test_un_registro_no_se_ve_desde_el_otro_contenedor(self):
        self._crear_item(ESQUEMA_A, 'Solo de A')

        with schema_context(ESQUEMA_B):
            self.assertFalse(GenItem.objects.filter(nombre='Solo de A').exists())

    def test_el_mismo_nombre_son_dos_filas_independientes(self):
        item_a = self._crear_item(ESQUEMA_A, 'Repetido')
        item_b = self._crear_item(ESQUEMA_B, 'Repetido')

        with schema_context(ESQUEMA_A):
            GenItem.objects.filter(pk=item_a.pk).update(nombre='Cambiado en A')

        with schema_context(ESQUEMA_B):
            self.assertEqual(GenItem.objects.get(pk=item_b.pk).nombre, 'Repetido')

    def test_las_secuencias_son_independientes(self):
        """
        Cada schema tiene su propia secuencia: la actividad de un contenedor no
        corre los ids del otro. Además de ser lo correcto, evita que el ritmo de
        uso de un cliente sea deducible desde otro contando los huecos.
        """
        with schema_context(ESQUEMA_B):
            anterior_b = GenItem.objects.create(nombre='Antes en B').pk

        with schema_context(ESQUEMA_A):
            for i in range(3):
                GenItem.objects.create(nombre=f'Ruido en A {i}')

        with schema_context(ESQUEMA_B):
            siguiente_b = GenItem.objects.create(nombre='Después en B').pk

        self.assertEqual(siguiente_b, anterior_b + 1)

    def test_la_cuenta_de_registros_no_incluye_al_otro(self):
        self._crear_item(ESQUEMA_A, 'A1')
        self._crear_item(ESQUEMA_A, 'A2')
        self._crear_item(ESQUEMA_B, 'B1')

        with schema_context(ESQUEMA_A):
            nombres_a = set(GenItem.objects.values_list('nombre', flat=True))
        with schema_context(ESQUEMA_B):
            nombres_b = set(GenItem.objects.values_list('nombre', flat=True))

        self.assertEqual(nombres_a & nombres_b, set())

    def test_las_tablas_de_tenant_no_existen_en_el_publico(self):
        """
        `gen_item` es de tenant: si apareciera en `public`, cualquier consulta hecha
        sin resolver contenedor escribiría en una tabla compartida por todos.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = 'gen_item'",
                [get_public_schema_name()],
            )
            self.assertIsNone(cursor.fetchone())

    def test_los_usuarios_si_son_compartidos(self):
        """
        El contrapositivo, para dejar la frontera escrita: la cuenta es global —una
        sola credencial para todos los contenedores— y por eso `seg_usuario` vive en
        el público y se ve igual desde cualquier schema. Lo aislado son los datos y
        los permisos, no la identidad.
        """
        with schema_context(ESQUEMA_A):
            desde_a = SegUsuario.objects.filter(email='ambos@ejemplo.com').exists()
        with schema_context(ESQUEMA_B):
            desde_b = SegUsuario.objects.filter(email='ambos@ejemplo.com').exists()

        self.assertTrue(desde_a)
        self.assertTrue(desde_b)


# --------------------------------------------------------------------------- #
# 2. El header X-Tenant
# --------------------------------------------------------------------------- #

class ResolucionDeTenantTests(AislamientoBase):
    """Qué schema resuelve `TenantHeaderMiddleware`, y qué rutas existen en cada uno."""

    def test_sin_header_las_rutas_de_tenant_no_existen(self):
        """
        Sin `X-Tenant` se sirve `urls_public`, donde `/general/` no está montado. La
        petición muere en el enrutador, antes de tocar ninguna vista.
        """
        respuesta = self._get(RUTA_ITEM, usuario=Escenario.sol_a)

        self.assertEqual(respuesta.status_code, 404)

    def test_header_con_el_schema_publico_opera_en_el_publico(self):
        respuesta = self._get(
            RUTA_ME, usuario=Escenario.sol_a, tenant=get_public_schema_name(),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['email'], 'sol.a@ejemplo.com')

    def test_tenant_inexistente_da_404(self):
        respuesta = self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant='no_existe')

        self.assertEqual(respuesta.status_code, 404)
        self.assertIn('no existe', respuesta.json()['detail'])

    def test_tenant_inexistente_no_revela_los_que_si_existen(self):
        respuesta = self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant='no_existe')

        cuerpo = respuesta.content.decode()
        self.assertNotIn(ESQUEMA_A, cuerpo)
        self.assertNotIn('Contenedor A', cuerpo)

    def test_el_miembro_entra_a_su_contenedor(self):
        respuesta = self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant=ESQUEMA_A)

        self.assertEqual(respuesta.status_code, 200)

    def test_sin_autenticar_no_entra_a_ningun_contenedor(self):
        respuesta = self._get(RUTA_ITEM, tenant=ESQUEMA_A)

        self.assertEqual(respuesta.status_code, 401)


# --------------------------------------------------------------------------- #
# 3. La membresía
# --------------------------------------------------------------------------- #

class MembresiaTests(AislamientoBase):
    """
    El header lo pone el cliente, así que resolver el schema no autoriza nada: la
    puerta es `EsMiembroDelTenant`.

    Todo esto va contra `RUTA_DOCUMENTO` a propósito — ver el comentario de la
    constante. Cada rechazo se afirma con su mensaje para que quede atado a esta
    capa y no a la de permisos, que rechazaría igual por otro motivo.
    """

    def _sin_membresia(self, respuesta):
        self.assertEqual(respuesta.status_code, 403, respuesta.content)
        self.assertEqual(respuesta.json()['detail'], MENSAJE_NO_MIEMBRO)

    def test_el_miembro_si_entra(self):
        """Control: sin esto, un 403 por cualquier otra causa haría pasar toda la clase."""
        respuesta = self._get(RUTA_DOCUMENTO, usuario=Escenario.ambos, tenant=ESQUEMA_B)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)

    def test_miembro_de_a_no_entra_a_b(self):
        self._sin_membresia(self._get(RUTA_DOCUMENTO, usuario=Escenario.sol_a, tenant=ESQUEMA_B))

    def test_el_rechazo_no_filtra_datos_del_otro_contenedor(self):
        self._crear_item(ESQUEMA_B, 'Secreto de B')

        respuesta = self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant=ESQUEMA_B)

        self.assertNotIn('Secreto de B', respuesta.content.decode())
        self.assertNotIn('Contenedor B', respuesta.content.decode())

    def test_usuario_sin_contenedores_no_entra_a_ninguno(self):
        for schema in (ESQUEMA_A, ESQUEMA_B):
            with self.subTest(schema=schema):
                self._sin_membresia(
                    self._get(RUTA_DOCUMENTO, usuario=Escenario.ajeno, tenant=schema)
                )

    def test_perder_la_membresia_cierra_el_acceso(self):
        antes = self._get(RUTA_DOCUMENTO, usuario=Escenario.ambos, tenant=ESQUEMA_B)

        SegUsuarioCliente.objects.filter(
            usuario=Escenario.ambos, cliente=Escenario.cliente_b,
        ).delete()

        self.assertEqual(antes.status_code, 200, antes.content)
        self._sin_membresia(self._get(RUTA_DOCUMENTO, usuario=Escenario.ambos, tenant=ESQUEMA_B))

    def test_la_escritura_ajena_se_corta_antes_de_llegar_a_la_vista(self):
        """El permiso corre antes que el handler, así que el borrado ni se intenta."""
        respuesta = self.client.delete(
            f'{RUTA_DOCUMENTO}1/', **self._headers(Escenario.sol_a, ESQUEMA_B),
        )

        self._sin_membresia(respuesta)

    def test_crear_en_un_contenedor_ajeno_no_deja_rastro(self):
        """Un 403 no puede haber creado nada: se verifica en el destino, no en la respuesta."""
        respuesta = self._post(
            RUTA_ITEM, {'nombre': 'Intruso'}, usuario=Escenario.sol_a, tenant=ESQUEMA_B,
        )

        self.assertEqual(respuesta.status_code, 403)
        with schema_context(ESQUEMA_B):
            self.assertFalse(GenItem.objects.filter(nombre='Intruso').exists())


# --------------------------------------------------------------------------- #
# 4. Los permisos
# --------------------------------------------------------------------------- #

class PermisosPorContenedorTests(AislamientoBase):
    """
    `UserTenantPermissions` es una tabla *de tenant*: el mismo usuario tiene una fila
    distinta por contenedor. Los grupos que lo autorizan en uno no existen en el otro.
    """

    def test_los_grupos_de_un_contenedor_no_autorizan_en_el_otro(self):
        creado_en_a = self._post(
            RUTA_ITEM, {'nombre': 'Item legítimo'}, usuario=Escenario.ambos, tenant=ESQUEMA_A,
        )
        creado_en_b = self._post(
            RUTA_ITEM, {'nombre': 'Item sin permiso'}, usuario=Escenario.ambos, tenant=ESQUEMA_B,
        )

        self.assertEqual(creado_en_a.status_code, 201, creado_en_a.content)
        # Mismo usuario, mismo token, misma ruta: lo único que cambia es el contenedor.
        self.assertEqual(creado_en_b.status_code, 403, creado_en_b.content)

    def test_ser_superusuario_en_un_contenedor_no_lo_es_en_el_otro(self):
        with schema_context(ESQUEMA_A):
            UserTenantPermissions.objects.filter(profile=Escenario.ambos).update(is_superuser=True)

        self.assertTrue(Escenario.cliente_a.es_superusuario(Escenario.ambos))
        self.assertFalse(Escenario.cliente_b.es_superusuario(Escenario.ambos))

    def test_la_lectura_solo_devuelve_lo_del_contenedor_del_header(self):
        self._crear_item(ESQUEMA_A, 'Item de A')
        self._crear_item(ESQUEMA_B, 'Item de B')

        desde_a = self._get(RUTA_ITEM, usuario=Escenario.ambos, tenant=ESQUEMA_A).json()
        nombres = [fila['nombre'] for fila in desde_a['results']]

        self.assertIn('Item de A', nombres)
        self.assertNotIn('Item de B', nombres)

    def test_el_id_de_un_registro_ajeno_no_resuelve(self):
        """
        El id de B no existe en el schema de A —o apunta a otro registro—, así que la
        vista responde 404 sin necesidad de una comprobación explícita de dueño.
        """
        with schema_context(ESQUEMA_B):
            GenItem.objects.all().delete()
            ajeno = GenItem.objects.create(nombre='Item de B')
        with schema_context(ESQUEMA_A):
            GenItem.objects.all().delete()

        respuesta = self._get(
            f'{RUTA_ITEM}{ajeno.pk}/', usuario=Escenario.ambos, tenant=ESQUEMA_A,
        )

        self.assertEqual(respuesta.status_code, 404)

    def test_una_escritura_cae_en_el_contenedor_del_header(self):
        respuesta = self._post(
            RUTA_ITEM, {'nombre': 'Nace en A'}, usuario=Escenario.sol_a, tenant=ESQUEMA_A,
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.content)

        with schema_context(ESQUEMA_A):
            self.assertTrue(GenItem.objects.filter(nombre='Nace en A').exists())
        with schema_context(ESQUEMA_B):
            self.assertFalse(GenItem.objects.filter(nombre='Nace en A').exists())


# --------------------------------------------------------------------------- #
# 5. La suscripción
# --------------------------------------------------------------------------- #

class SuscripcionPorContenedorTests(AislamientoBase):
    """
    El corte por falta de pago también es por contenedor: que a uno se le venza la
    suscripción no puede afectar a los demás, ni siquiera para el usuario que está
    en los dos.
    """

    def _vencer(self, cliente):
        CtnSuscripcion.objects.filter(pk=cliente.suscripcion_id).update(
            fecha_fin=timezone.localdate() - timedelta(days=1),
        )

    def test_la_suscripcion_vencida_cierra_solo_su_contenedor(self):
        self._vencer(Escenario.cliente_b)

        en_b = self._get(RUTA_DOCUMENTO, usuario=Escenario.ambos, tenant=ESQUEMA_B)
        en_a = self._get(RUTA_DOCUMENTO, usuario=Escenario.ambos, tenant=ESQUEMA_A)

        self.assertEqual(en_b.status_code, 403)
        self.assertEqual(en_b.json()['codigo'], 'suscripcion_vencida')
        self.assertEqual(en_a.status_code, 200)

    def test_un_anonimo_no_averigua_el_estado_de_la_suscripcion(self):
        """
        La comprobación se movió de un middleware a un permission justamente por esto:
        sin usuario resuelto, cualquiera podía sondear contenedores con `X-Tenant`.
        """
        self._vencer(Escenario.cliente_b)

        respuesta = self._get(RUTA_DOCUMENTO, tenant=ESQUEMA_B)

        self.assertEqual(respuesta.status_code, 401)
        self.assertNotIn('suscripcion_vencida', respuesta.content.decode())


# --------------------------------------------------------------------------- #
# 6. Fugas entre peticiones
# --------------------------------------------------------------------------- #

class ContaminacionEntrePeticionesTests(AislamientoBase):
    """
    El riesgo que no se ve en una petición aislada: el proceso es de larga vida y la
    conexión se reusa. Si el schema resuelto sobrevive a la petición que lo fijó, la
    siguiente lee del contenedor equivocado — y el usuario ni se entera.
    """

    def test_el_schema_no_sobrevive_a_la_peticion(self):
        self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant=ESQUEMA_A)

        respuesta = self._get(RUTA_ME, usuario=Escenario.sol_b)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(connection.schema_name, get_public_schema_name())

    def test_dos_contenedores_seguidos_no_se_mezclan(self):
        self._crear_item(ESQUEMA_A, 'Item de A')
        self._crear_item(ESQUEMA_B, 'Item de B')

        primera = self._get(RUTA_ITEM, usuario=Escenario.ambos, tenant=ESQUEMA_A).json()
        segunda = self._get(RUTA_ITEM, usuario=Escenario.sol_b, tenant=ESQUEMA_B).json()

        self.assertNotIn('Item de B', [fila['nombre'] for fila in primera['results']])
        self.assertNotIn('Item de A', [fila['nombre'] for fila in segunda['results']])

    def test_un_tenant_inexistente_no_deja_pegado_el_anterior(self):
        self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant=ESQUEMA_A)
        self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant='no_existe')

        respuesta = self._get(RUTA_ME, usuario=Escenario.sol_a)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(connection.schema_name, get_public_schema_name())

    def test_el_usuario_actual_no_se_filtra_entre_peticiones(self):
        """
        `_usuario_actual` es un contextvar que alimenta la auditoría. Si no se
        reseteara, el `gen_log` de un contenedor quedaría firmado por el usuario de
        la petición anterior, que puede ser de otro cliente.
        """
        from seguridad.contexto import obtener_usuario_actual

        self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant=ESQUEMA_A)

        self.assertIsNone(obtener_usuario_actual())


# --------------------------------------------------------------------------- #
# 7. Barrido de todos los endpoints de tenant
# --------------------------------------------------------------------------- #

class BarridoDeEndpointsTests(AislamientoBase):
    """
    Las clases anteriores prueban el mecanismo a fondo sobre dos endpoints. Esta prueba
    lo contrario: poco, pero sobre **todos** — que ninguno de los 94 viewsets servidos
    dentro de un contenedor se salte la puerta de entrada.

    Su valor real es el futuro: un viewset registrado mañana con
    `permission_classes = [IsAuthenticated]` o con `AllowAny` rompe esta clase el mismo
    día, sin que nadie tenga que acordarse de escribirle una prueba.

    Lo que **no** prueba: que el contenido de la respuesta no traiga datos ajenos. Eso
    exige construir datos válidos modelo por modelo y está cubierto solo para `item` y
    `documento`. Un endpoint puede pasar este barrido y aun así filtrar por dentro —
    con un `get_queryset` que consulte el público, un `raw()` o un FK cruzado.
    """

    def test_el_barrido_cubre_todos_los_viewsets(self):
        """
        Guarda del propio barrido: si un viewset no resuelve a ninguna URL, se queda sin
        probar. Sin esta prueba eso pasaría en silencio y el barrido se vería verde.
        """
        rutas = rutas_de_tenant()
        sin_ruta = [etiqueta for etiqueta, url in rutas if url is None]

        self.assertEqual(sin_ruta, [], 'viewsets sin URL resoluble: quedarían sin barrer')
        # Una URL distinta por viewset: si dos comparten URL, uno no se está probando.
        urls = [url for _, url in rutas]
        self.assertEqual(len(set(urls)), len(urls), 'dos viewsets resolvieron a la misma URL')
        self.assertGreaterEqual(len(rutas), 94)

    def test_ningun_endpoint_le_responde_a_un_no_miembro(self):
        """
        `fantasma` tiene todos los permisos de modelo en B pero no es miembro de B, así
        que un 403 acá solo lo puede producir `EsMiembroDelTenant`. Si en vez de 403
        aparece cualquier otra cosa —200, 404, 405, 500—, la petición pasó la puerta.
        """
        for etiqueta, url in rutas_de_tenant():
            with self.subTest(endpoint=etiqueta):
                respuesta = self._get(url, usuario=Escenario.fantasma, tenant=ESQUEMA_B)
                self.assertEqual(respuesta.status_code, 403, f'{url} -> {respuesta.content[:200]}')

    def test_ningun_endpoint_le_responde_a_un_anonimo(self):
        for etiqueta, url in rutas_de_tenant():
            with self.subTest(endpoint=etiqueta):
                respuesta = self._get(url, tenant=ESQUEMA_B)
                self.assertEqual(respuesta.status_code, 401, f'{url} -> {respuesta.content[:200]}')

    def test_ningun_endpoint_de_tenant_existe_en_el_schema_publico(self):
        """Sin `X-Tenant` se sirve `urls_public`, donde estas rutas no están montadas."""
        for etiqueta, url in rutas_de_tenant():
            with self.subTest(endpoint=etiqueta):
                respuesta = self._get(url, usuario=Escenario.sol_a)
                self.assertEqual(respuesta.status_code, 404, f'{url} -> {respuesta.status_code}')
