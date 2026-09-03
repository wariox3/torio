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

import importlib
from unittest import mock
import itertools
import json
import uuid as uuid_lib
from datetime import date, time, timedelta

from django.contrib.auth.models import Group, Permission
from django.db import connection, models as campos_db, transaction
from django.db.models.fields import NOT_PROVIDED
from django.test import TestCase
from django.urls import Resolver404, resolve
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import mixins
from rest_framework_simplejwt.tokens import RefreshToken
from tenant_users.permissions.models import UserTenantPermissions

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo
from general.models import GenArchivo, GenArchivoTipo, GenItem, GenModelo
from seguridad.models import SegUsuario, SegUsuarioCliente
from utilidades import backblaze

ESQUEMA_A = 'aislamiento_a'
ESQUEMA_B = 'aislamiento_b'

RUTA_ITEM = '/general/item/'
RUTA_ME = '/seguridad/me/'
# Ruta con la que se prueba la **membresía**, y por eso tiene un requisito que hay que
# respetar al cambiarla: su viewset debe quedarse con las permission_classes por defecto
# (`EsMiembroDelTenant` + `SuscripcionVigente`), sin permiso de modelo encima. Solo así un
# 403 acá prueba que falló la membresía.
#
# `GenItemViewSet`, en cambio, declara `TienePermisoModelo`, así que un 403 suyo puede
# venir de la membresía o de los permisos. Confundir las dos cosas deja pasar mutaciones:
# con `EsMiembroDelTenant` desactivado, un extraño sigue recibiendo 403 en `/general/item/`
# porque tampoco tiene permisos de modelo en ese contenedor.
#
# Antes era `/general/documento/`, hasta que a `GenDocumento` (tipo Movimiento) se le
# agregó `TienePermisoModelo`. `GenDocumentoDetalle` es tipo Detalle, que por diseño no se
# restringe por permisos, así que es estable para este uso. Si algún día también se
# protege, hay que mover esta constante a otro endpoint sin permiso de modelo —
# `test_la_ruta_de_membresia_no_exige_permiso_de_modelo` falla si eso pasa.
RUTA_DOCUMENTO = '/general/documento-detalle/'

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
    | `pleno`    | A y B      | **todos**, en A y en B         |

    `ambos` es el caso interesante para las fugas: como es miembro legítimo de los dos,
    cualquier mezcla se le manifiesta sin necesidad de forjar nada.

    `fantasma` es el que hace medible el barrido de endpoints. Tiene fila de
    `UserTenantPermissions` en B con todos los permisos de modelo, pero **no** tiene
    `SegUsuarioCliente`: es el estado que quedaría si una baja de membresía fallara a
    medias. Sin él, un 403 en los 94 endpoints no probaría nada, porque los que exigen
    permiso de modelo rechazarían igual a cualquier extraño y el barrido pasaría aunque
    la membresía estuviera desactivada — el mismo falso positivo que ya nos mordió en
    `MembresiaTests`. Con él, el único motivo posible de 403 es `EsMiembroDelTenant`.

    `pleno` es el que usa la cobertura de contenido: miembro de los dos y con todos los
    permisos en los dos, para que un rechazo nunca venga de la autorización y lo único
    que se esté midiendo sea qué datos devuelve cada contenedor.
    """

    cliente_a = None
    cliente_b = None
    sol_a = None
    sol_b = None
    ambos = None
    ajeno = None
    fantasma = None
    pleno = None


def _crear_contenedor(schema, nombre, dominio):
    """Crea el tenant con su schema real, su dominio y una suscripción vigente."""
    cliente = CtnCliente(
        schema_name=schema,
        nombre=nombre,
        celular='+573000000000',
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
        Escenario.pleno = SegUsuario.objects.create(
            email='pleno@ejemplo.com', is_active=True, is_verified=True,
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

        Escenario.cliente_a.add_user(Escenario.pleno, grupos=[grupo_todo])
        Escenario.cliente_b.add_user(Escenario.pleno, grupos=[grupo_todo])


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

        # Control positivo: sin esto, la intersección vacía se cumpliría igual con los
        # dos conjuntos vacíos y la prueba no diría nada.
        self.assertEqual(nombres_a, {'A1', 'A2'})
        self.assertEqual(nombres_b, {'B1'})
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
        # Control: que la respuesta sea la esperada, y no un cuerpo vacío que haría pasar
        # las dos aserciones de abajo sin haber ejercitado nada.
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn('no_existe', cuerpo)
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

    def test_la_ruta_de_membresia_no_exige_permiso_de_modelo(self):
        """
        Guarda de la constante, no del código de producción: si al viewset de
        `RUTA_DOCUMENTO` le agregan `TienePermisoModelo`, sus 403 pasarían a poder venir
        de los permisos y esta clase dejaría de probar la membresía sin avisar. Ya pasó
        una vez con `/general/documento/`.
        """
        vista = resolve(RUTA_DOCUMENTO, urlconf='torioapp.urls_tenant').func.cls

        self.assertNotIn(
            'TienePermisoModelo',
            [clase.__name__ for clase in vista.permission_classes],
            f'{RUTA_DOCUMENTO} ya no sirve para probar la membresía: mové la constante',
        )

    def test_el_miembro_si_entra(self):
        """Control: sin esto, un 403 por cualquier otra causa haría pasar toda la clase."""
        respuesta = self._get(RUTA_DOCUMENTO, usuario=Escenario.ambos, tenant=ESQUEMA_B)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)

    def test_miembro_de_a_no_entra_a_b(self):
        self._sin_membresia(self._get(RUTA_DOCUMENTO, usuario=Escenario.sol_a, tenant=ESQUEMA_B))

    def test_el_rechazo_no_filtra_datos_del_otro_contenedor(self):
        self._crear_item(ESQUEMA_B, 'Secreto de B')

        respuesta = self._get(RUTA_ITEM, usuario=Escenario.sol_a, tenant=ESQUEMA_B)

        # Control positivo: el mismo dato, pedido por alguien que sí es de B, aparece.
        # Sin esto, un `Secreto de B` que nunca se hubiera creado —o un endpoint roto
        # devolviendo vacío— haría pasar la prueba sin probar el aislamiento.
        legitimo = self._get(RUTA_ITEM, usuario=Escenario.sol_b, tenant=ESQUEMA_B)
        self.assertEqual(legitimo.status_code, 200)
        self.assertIn('Secreto de B', legitimo.content.decode())

        self.assertEqual(respuesta.status_code, 403)
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

        respuesta_a = self._get(RUTA_ITEM, usuario=Escenario.ambos, tenant=ESQUEMA_A)
        respuesta_b = self._get(RUTA_ITEM, usuario=Escenario.sol_b, tenant=ESQUEMA_B)

        self.assertEqual(respuesta_a.status_code, 200)
        self.assertEqual(respuesta_b.status_code, 200)
        nombres_a = [fila['nombre'] for fila in respuesta_a.json()['results']]
        nombres_b = [fila['nombre'] for fila in respuesta_b.json()['results']]

        # Control positivo: cada contenedor devuelve lo suyo. Con dos listas vacías las
        # dos aserciones de ausencia se cumplirían igual.
        self.assertIn('Item de A', nombres_a)
        self.assertIn('Item de B', nombres_b)
        self.assertNotIn('Item de B', nombres_a)
        self.assertNotIn('Item de A', nombres_b)

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


# --------------------------------------------------------------------------- #
# 8. Aislamiento de contenido, endpoint por endpoint
# --------------------------------------------------------------------------- #
#
# El barrido de la sección 7 prueba que la puerta está cerrada para quien no es
# miembro. Esto prueba lo otro, que es lo que un cliente pregunta de verdad: que un
# miembro **legítimo** de B no vea, ni pueda tocar, datos de A.
#
# La diferencia no es teórica. Una fuga dentro de un `get_queryset` —un
# `schema_context` mal puesto, un `raw()`, un FK cruzado— pasa entera por el barrido,
# porque el 403 del no-miembro ocurre antes de que la vista llegue a consultar nada.

# Marcadores. Dos señales independientes, porque ninguna sola alcanza:
#
#   1. El rango de id. Cada contenedor crea sus filas con PK explícita en su rango, así
#      que un id >= ID_FRONTERA en una respuesta de B es dato de A sin ambigüedad. Es la
#      única señal que funciona en los modelos sin campo de texto en su serializer, y es
#      lo que permite pedir por id un registro ajeno.
#   2. El marcador de texto, en los modelos que tienen un Char/Text expuesto. Atrapa
#      también las fugas que aparecen dentro de un campo anidado del serializer.
MARCADOR = {ESQUEMA_A: 'MARCA-TENANT-A', ESQUEMA_B: 'MARCA-TENANT-B'}
BASE_ID = {ESQUEMA_A: 900001, ESQUEMA_B: 800001}
ID_FRONTERA = 900000

_FECHA = date(2026, 6, 1)


def _es_obligatorio(campo):
    """
    Campo que hay que llenar sí o sí para que el INSERT no reviente.

    Las FKs NOT NULL entran aunque tengan `default`: varias apuntan por defecto al id 1
    de un catálogo (`GenArchivo.archivo_tipo`, por ejemplo) y en los contenedores de
    prueba los fixtures no están cargados, así que ese id no existe y el default deja
    una FK colgando.
    """
    if campo.primary_key or campo.auto_created:
        return False
    if campo.is_relation:
        return not campo.null
    return not (campo.null or campo.has_default() or campo.db_default is not NOT_PROVIDED)


def endpoints_de_contenido():
    """
    [(etiqueta, viewset, modelo, url)] de los endpoints con ruta de lista que devuelven
    datos del cliente.

    Se excluyen los catálogos (`GenModelo.tipo == 'F'`): su contenido es el mismo en
    todos los contenedores porque sale del mismo JSON, así que un marcador ahí no
    distingue nada. Siguen cubiertos por el barrido de puerta.
    """
    with open('general/fixtures/15_modelo.json') as archivo:
        tipos = {r['clase']: r['tipo'] for r in json.load(archivo)['data']}

    salida = []
    for montaje, modulo in MONTAJES:
        for prefijo, viewset, _ in importlib.import_module(modulo).router.registry:
            qs = getattr(viewset, 'queryset', None)
            modelo = qs.model if qs is not None else getattr(
                getattr(getattr(viewset, 'serializer_class', None), 'Meta', None), 'model', None
            )
            if modelo is None or tipos.get(modelo.__name__) == 'F':
                continue
            if not issubclass(viewset, mixins.ListModelMixin):
                continue
            salida.append((f'{montaje}/{prefijo}', viewset, modelo, f'/{montaje}/{prefijo}/'))
    return salida


class _Constructor:
    """
    Crea la fila mínima de cualquier modelo, resolviendo sus FKs en cascada.

    Se descartó escribir 39 factories a mano: envejecen mal y el día que alguien agregue
    un campo obligatorio hay que tocarlas una por una. Acá se introspecciona qué exige
    de verdad la base —`null=False`, sin `default` ni `db_default`— y se llena por tipo.

    La PK se fija a mano siempre, desde el contador del contenedor, por dos razones: los
    rangos quedan disjuntos entre A y B (que es la señal de fuga), y de paso se resuelven
    los modelos con PK manual, que en este proyecto son varios.
    """

    # Lo que la introspección no puede adivinar.
    EXCEPCIONES = {
        # Tabla del schema público: su aislamiento es por filtro de queryset, no por
        # schema, y el FK a CtnCliente tiene que ser el contenedor real — crear uno
        # nuevo levantaría otro schema de PostgreSQL.
        'SegUsuarioCliente': lambda constructor: {
            'usuario': SegUsuario.objects.create(
                email=f'contenido-{constructor.siguiente_id()}@ejemplo.com', is_active=True,
            ),
            'cliente': constructor.cliente,
        },
        # `ConPeriodo` deriva su PK en `save()` (anio*100+mes) e ignora el id explícito
        # que pone `_pk`, así que es el único modelo que no puede recibir su rango por
        # esa vía: hay que dárselo a través del año.
        'ConPeriodo': lambda constructor: constructor.periodo_en_rango(),
    }

    def __init__(self, schema, cliente):
        self.schema = schema
        self.cliente = cliente
        self.marcador = MARCADOR[schema]
        self._contador = itertools.count(BASE_ID[schema])
        self._mes_periodo = itertools.count(1)
        self._cache = {}

    def siguiente_id(self):
        return next(self._contador)

    def periodo_en_rango(self):
        """
        `anio` y `mes` de un `ConPeriodo` que caiga en el rango del contenedor.

        El año sale del propio `BASE_ID` para que la PK derivada quede donde la señal
        de fuga la espera: 9000 en A da 900001+, 8000 en B da 800001+. Son años
        absurdos, y es a propósito — los validadores de rango de `anio` solo corren en
        el serializer, no en `save()`, y acá lo que importa es que los rangos de A y B
        queden disjuntos. El mes lleva su propio contador porque `unique_together`
        cubre (anio, mes) y en cada contenedor se crea más de un periodo: uno para el
        endpoint y otro como FK de `ConMovimiento`.
        """
        return {'anio': BASE_ID[self.schema] // 100, 'mes': next(self._mes_periodo)}

    def crear(self, modelo, marcar=True):
        """
        Cada creación va en su propio savepoint: sin eso, el primer INSERT que falle deja
        la transacción rota y los 22 modelos siguientes fallan en cascada con un error
        que no dice nada de ellos.
        """
        cacheados = set(self._cache)
        try:
            with transaction.atomic():
                return self._crear(modelo, marcar)
        except Exception:
            # Lo que se creó dentro del savepoint ya no existe: sacarlo de la caché.
            for clave in set(self._cache) - cacheados:
                del self._cache[clave]
            raise

    def _crear(self, modelo, marcar=True):
        # Primero las excepciones: si la introspección corriera antes, intentaría
        # construir por su cuenta los FKs que la excepción viene a resolver.
        datos = dict(self.EXCEPCIONES.get(modelo.__name__, lambda _: {})(self))

        for campo in modelo._meta.concrete_fields:
            if campo.name in datos or not _es_obligatorio(campo):
                continue
            datos[campo.name] = self._valor(campo)

        if marcar:
            datos.update(self._campo_marcable(modelo, datos))

        datos[modelo._meta.pk.name] = self._pk(modelo)
        return modelo.objects.create(**datos)

    def _pk(self, modelo):
        """Id explícito del rango del contenedor. Si la PK es texto, el número va como cadena."""
        valor = self.siguiente_id()
        pk = modelo._meta.pk
        return str(valor)[:pk.max_length] if isinstance(pk, campos_db.CharField) else valor

    def _campo_marcable(self, modelo, ya_puestos):
        """
        Escribe el marcador en un campo de texto que el serializer devuelva.

        Se prefiere uno opcional que uno obligatorio: los obligatorios muchas veces son
        códigos con `max_length` corto donde el marcador quedaría recortado e
        irreconocible.
        """
        for campo in modelo._meta.concrete_fields:
            if campo.name in ya_puestos or campo.primary_key or campo.choices:
                continue
            if not isinstance(campo, (campos_db.CharField, campos_db.TextField)):
                continue
            if isinstance(campo, campos_db.EmailField):
                continue
            if campo.max_length is not None and campo.max_length < len(self.marcador) + 8:
                continue
            return {campo.name: f'{self.marcador}-{self.siguiente_id()}'}
        return {}

    def _relacionado(self, modelo):
        """Una instancia por modelo y por contenedor: las FKs comparten destino."""
        if modelo.__name__ not in self._cache:
            self._cache[modelo.__name__] = self.crear(modelo, marcar=False)
        return self._cache[modelo.__name__]

    def _valor(self, campo):
        if campo.is_relation:
            return self._relacionado(campo.related_model)

        if isinstance(campo, campos_db.EmailField):
            return f'marca{self.siguiente_id()}@ejemplo.com'
        if isinstance(campo, (campos_db.CharField, campos_db.TextField)):
            if campo.choices:
                return campo.choices[0][0]
            # El sufijo evita chocar con constraints únicos —`ConCuenta.codigo` es uno—
            # sin perder el prefijo, que es lo que buscan las aserciones.
            texto = f'{self.marcador}-{self.siguiente_id()}'
            if campo.max_length and campo.max_length < len(texto):
                # No cabe entero. Si además es único, el marcador truncado colisionaría
                # (`TurTurno.codigo` son 10 caracteres): ahí manda la unicidad.
                if campo.unique:
                    return str(self.siguiente_id())[-campo.max_length:]
                return texto[:campo.max_length]
            return texto
        if isinstance(campo, campos_db.DateTimeField):
            return timezone.now()
        if isinstance(campo, campos_db.DateField):
            return _FECHA
        if isinstance(campo, campos_db.TimeField):
            return time(8, 0)
        if isinstance(campo, campos_db.BooleanField):
            return False
        if isinstance(campo, campos_db.UUIDField):
            return uuid_lib.uuid4()
        if isinstance(campo, campos_db.JSONField):
            return {}
        if isinstance(campo, (campos_db.DecimalField, campos_db.FloatField)):
            return 0
        if isinstance(campo, campos_db.IntegerField):
            # Valor distinto por fila: hay enteros bajo `unique_together` y con un 1 fijo
            # la segunda fila chocaría contra la primera.
            return self.siguiente_id()
        return self.marcador


class ContenidoPorEndpointTests(AislamientoBase):
    """
    Un miembro legítimo de B no ve, ni puede tocar, datos de A. Endpoint por endpoint.

    Todo se hace como `pleno`, que es miembro de los dos contenedores y tiene todos los
    permisos en los dos: así ningún resultado se explica por autorización, y lo único que
    se mide es qué datos devuelve cada schema.

    Los datos se construyen una vez por clase en los dos contenedores. Si un modelo no se
    puede construir, **no se salta**: `test_el_escenario_cubre_todos_los_endpoints` falla
    y lo nombra, porque un endpoint silenciosamente sin datos es una prueba que pasa sin
    probar nada.
    """

    datos = {}
    fallos = {}

    # Endpoints cuya lista exige parámetros. `usuario-cliente-permiso` filtra por usuario
    # y sin `usuario_id` responde 400.
    PARAMS = {
        'seguridad/usuario-cliente-permiso': lambda datos, schema, etiqueta: {
            'usuario_id': datos[schema][etiqueta].usuario_id,
        },
    }

    @classmethod
    def setUpTestData(cls):
        cls.datos = {ESQUEMA_A: {}, ESQUEMA_B: {}}
        cls.fallos = {}
        for schema, cliente in ((ESQUEMA_A, Escenario.cliente_a), (ESQUEMA_B, Escenario.cliente_b)):
            constructor = _Constructor(schema, cliente)
            with schema_context(schema):
                for etiqueta, _, modelo, _ in endpoints_de_contenido():
                    try:
                        cls.datos[schema][etiqueta] = constructor.crear(modelo)
                    except Exception as e:  # noqa: BLE001 — se reporta, no se traga
                        cls.fallos.setdefault(etiqueta, f'{type(e).__name__}: {str(e)[:160]}')

    def _cubiertos(self):
        """Endpoints con dato construido en los dos contenedores."""
        for etiqueta, viewset, modelo, url in endpoints_de_contenido():
            if etiqueta in self.fallos:
                continue
            yield etiqueta, viewset, modelo, url

    def _params(self, etiqueta, schema):
        constructor = self.PARAMS.get(etiqueta)
        return constructor(self.datos, schema, etiqueta) if constructor else {}

    @staticmethod
    def _filas(respuesta):
        cuerpo = respuesta.json()
        return cuerpo['results'] if isinstance(cuerpo, dict) and 'results' in cuerpo else cuerpo

    # ── Guarda del escenario ────────────────────────────────────────────────

    def test_el_escenario_cubre_todos_los_endpoints(self):
        """
        Sin esta guarda, un modelo que el constructor no sepa armar desaparecería del
        recorrido y la clase seguiría en verde con menos cobertura de la que dice tener.
        """
        self.assertEqual(
            self.fallos, {},
            'endpoints sin dato construido: quedarían sin cobertura de contenido',
        )
        self.assertEqual(len(list(self._cubiertos())), len(endpoints_de_contenido()))

    # ── Lectura ─────────────────────────────────────────────────────────────

    def test_la_lista_no_trae_datos_del_otro_contenedor(self):
        for etiqueta, _, _, url in self._cubiertos():
            with self.subTest(endpoint=etiqueta):
                respuesta = self._get(url, usuario=Escenario.pleno, tenant=ESQUEMA_B,
                                      data=self._params(etiqueta, ESQUEMA_B))
                self.assertEqual(respuesta.status_code, 200, respuesta.content[:200])

                cuerpo = respuesta.content.decode()
                self.assertNotIn(MARCADOR[ESQUEMA_A], cuerpo, f'{url} filtró el marcador de A')
                ajenos = [f['id'] for f in self._filas(respuesta)
                          if isinstance(f.get('id'), int) and f['id'] >= ID_FRONTERA]
                self.assertEqual(ajenos, [], f'{url} devolvió ids del contenedor A')

    def test_la_lista_si_trae_los_datos_propios(self):
        """
        Control positivo. Sin esto, todas las pruebas de arriba pasarían con una lista
        vacía —o con el endpoint roto devolviendo `[]`— y no probarían absolutamente nada.
        """
        for etiqueta, _, _, url in self._cubiertos():
            with self.subTest(endpoint=etiqueta):
                respuesta = self._get(url, usuario=Escenario.pleno, tenant=ESQUEMA_B,
                                      data=self._params(etiqueta, ESQUEMA_B))
                propio = self.datos[ESQUEMA_B][etiqueta]
                ids = [f.get('id') for f in self._filas(respuesta)]
                self.assertIn(propio.pk, ids, f'{url} no devolvió el registro propio de B')

    def test_el_detalle_de_un_registro_ajeno_no_resuelve(self):
        for etiqueta, viewset, _, url in self._cubiertos():
            if not issubclass(viewset, mixins.RetrieveModelMixin):
                continue
            with self.subTest(endpoint=etiqueta):
                ajeno = self.datos[ESQUEMA_A][etiqueta]
                respuesta = self._get(f'{url}{ajeno.pk}/', usuario=Escenario.pleno, tenant=ESQUEMA_B)
                self.assertEqual(respuesta.status_code, 404, f'{url}{ajeno.pk}/ resolvió')

    # ── Escritura ───────────────────────────────────────────────────────────

    def test_patch_sobre_un_registro_ajeno_no_lo_modifica(self):
        """
        La verificación va contra el schema de A, no contra el código de respuesta: lo
        que hay que probar es que el registro **no cambió**, no que la API dijo que no.
        """
        for etiqueta, viewset, modelo, url in self._cubiertos():
            if not issubclass(viewset, mixins.UpdateModelMixin):
                continue
            with self.subTest(endpoint=etiqueta):
                ajeno = self.datos[ESQUEMA_A][etiqueta]
                campo, antes = self._campo_testigo(ajeno)

                respuesta = self.client.patch(
                    f'{url}{ajeno.pk}/', {campo: 'PISADO-DESDE-B'} if campo else {},
                    content_type='application/json',
                    **self._headers(Escenario.pleno, ESQUEMA_B),
                )

                self.assertNotIn(respuesta.status_code, (200, 201, 202, 204),
                                 f'{url}{ajeno.pk}/ aceptó un PATCH desde otro contenedor')
                with schema_context(ESQUEMA_A):
                    vigente = modelo.objects.get(pk=ajeno.pk)
                    self.assertEqual(getattr(vigente, campo) if campo else None, antes)

    def test_delete_sobre_un_registro_ajeno_no_lo_borra(self):
        for etiqueta, viewset, modelo, url in self._cubiertos():
            if not issubclass(viewset, mixins.DestroyModelMixin):
                continue
            with self.subTest(endpoint=etiqueta):
                ajeno = self.datos[ESQUEMA_A][etiqueta]

                respuesta = self.client.delete(
                    f'{url}{ajeno.pk}/', **self._headers(Escenario.pleno, ESQUEMA_B),
                )

                self.assertNotIn(respuesta.status_code, (200, 202, 204),
                                 f'{url}{ajeno.pk}/ aceptó un DELETE desde otro contenedor')
                with schema_context(ESQUEMA_A):
                    self.assertTrue(
                        modelo.objects.filter(pk=ajeno.pk).exists(),
                        f'{url}{ajeno.pk}/ borró un registro del contenedor A',
                    )

    @staticmethod
    def _campo_testigo(instancia):
        """El campo de texto donde quedó el marcador, para comprobar que no lo pisaron."""
        for campo in instancia._meta.concrete_fields:
            if isinstance(campo, (campos_db.CharField, campos_db.TextField)):
                if getattr(instancia, campo.name, None) == MARCADOR[ESQUEMA_A]:
                    return campo.name, MARCADOR[ESQUEMA_A]
        return None, None

    def test_los_permisos_de_un_usuario_de_otro_contenedor_no_se_ven(self):
        """
        `seguridad/usuario-cliente-permiso` merece su propia prueba: `SegUsuarioCliente`
        vive en el schema **público**, así que las filas de los dos contenedores están en
        la misma tabla. Acá el aislamiento no lo da PostgreSQL, lo da el filtro del
        queryset — que es exactamente el tipo de defensa que se rompe en un refactor.
        """
        etiqueta = 'seguridad/usuario-cliente-permiso'
        ajeno = self.datos[ESQUEMA_A][etiqueta]

        respuesta = self._get(
            f'/{etiqueta}/', usuario=Escenario.pleno, tenant=ESQUEMA_B,
            data={'usuario_id': ajeno.usuario_id},
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content[:200])
        self.assertEqual(self._filas(respuesta), [],
                         'se vieron los permisos de un usuario que no es miembro de B')


# --------------------------------------------------------------------------- #
# 7. La descarga de archivos
# --------------------------------------------------------------------------- #

class DescargaDeArchivosTests(AislamientoBase):
    """
    `GET /general/archivo/<pk>/descargar/` sirve el contenido desde el back,
    porque el bucket es privado y su URL directa responde 401.

    Eso mueve la frontera: al archivo ya no lo protege B2 sino este endpoint.
    Quien lo aísla sigue siendo el schema —el manager de Django solo ve la tabla
    del contenedor resuelto—, y encima va `EsMiembroDelTenant`. `get_object` no
    aporta aislamiento: aporta el 404 cuando la fila no está en este schema.

    El mismo número de pk identifica archivos distintos en A y en B, que es justo
    la confusión que hay que descartar; los pk van explícitos porque las
    secuencias de PostgreSQL no se revierten con el rollback del TestCase.

    B2 se mockea a propósito: acá se mide quién puede pedir qué, no la red.

    Poder de detección medido por mutación:

    | Mutante                                  | Lo acusa                        |
    |------------------------------------------|---------------------------------|
    | `get_object` → `objects.get(pk=...)`     | los dos tests de 404            |
    | el viewset deja de exigir membresía      | `test_quien_no_es_miembro...`   |
    """

    @staticmethod
    def _crear_archivo(schema, contenido_marcado, pk=None):
        with schema_context(schema):
            GenArchivoTipo.objects.get_or_create(
                id=1, defaults={'codigo': 'general', 'nombre': 'General'},
            )
            # `GenModelo.id` es manual (BigIntegerField), no autoincremental:
            # el 10004 es el que trae el fixture para GenItem.
            modelo, _ = GenModelo.objects.get_or_create(
                id=10004,
                defaults={
                    'app': 'general', 'clase': 'GenItem', 'nombre': 'Item',
                    'tabla': 'gen_item', 'tipo': 'A',
                },
            )
            item = GenItem.objects.create(nombre=f'Dueño de {schema}')
            # El pk va explícito cuando el test necesita el mismo número en los
            # dos schemas: las secuencias de PostgreSQL no se revierten con el
            # rollback del TestCase, así que coincidir por casualidad no dura.
            return GenArchivo.objects.create(
                pk=pk, archivo_tipo_id=1, modelo=modelo, objeto_id=str(item.pk),
                nombre=f'{contenido_marcado}.pdf', tipo='application/pdf', tamano=10,
                almacenamiento_id=f'{schema}/archivos/{modelo.pk}/2026/08/{contenido_marcado}.pdf',
            )

    def _descargar(self, pk, usuario, tenant, contenido=b'contenido'):
        with mock.patch.object(backblaze, 'descargar', return_value=contenido) as descargar:
            respuesta = self._get(f'/general/archivo/{pk}/descargar/', usuario=usuario, tenant=tenant)
        return respuesta, descargar

    def test_el_miembro_descarga_el_archivo_de_su_contenedor(self):
        """Control: sin esto, un 404 por cualquier causa haría pasar toda la clase."""
        archivo_b = self._crear_archivo(ESQUEMA_B, 'secreto_de_b')

        respuesta, descargar = self._descargar(archivo_b.pk, Escenario.ambos, ESQUEMA_B)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(descargar.call_args.args[1], archivo_b.almacenamiento_id)

    def test_el_mismo_pk_en_el_otro_contenedor_no_trae_el_archivo_ajeno(self):
        """
        `ambos` es miembro legítimo de A y de B, así que acá no hay nada forjado:
        pide un pk que existe en los dos y tiene que recibir el de A.
        """
        archivo_a = self._crear_archivo(ESQUEMA_A, 'secreto_de_a', pk=777)
        archivo_b = self._crear_archivo(ESQUEMA_B, 'secreto_de_b', pk=777)
        self.assertEqual(archivo_a.pk, archivo_b.pk, 'el escenario perdió sentido si difieren')

        respuesta, descargar = self._descargar(archivo_b.pk, Escenario.ambos, ESQUEMA_A)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        key_pedida = descargar.call_args.args[1]
        self.assertEqual(key_pedida, archivo_a.almacenamiento_id)
        self.assertNotIn('secreto_de_b', key_pedida)

    def test_un_pk_que_solo_existe_en_el_otro_contenedor_da_404(self):
        archivo_b = self._crear_archivo(ESQUEMA_B, 'solo_en_b')
        with schema_context(ESQUEMA_A):
            self.assertFalse(GenArchivo.objects.filter(pk=archivo_b.pk).exists())

        respuesta, descargar = self._descargar(archivo_b.pk, Escenario.ambos, ESQUEMA_A)

        self.assertEqual(respuesta.status_code, 404, respuesta.content)
        descargar.assert_not_called()

    def test_quien_no_es_miembro_no_descarga_ni_toca_b2(self):
        archivo_b = self._crear_archivo(ESQUEMA_B, 'secreto_de_b')

        respuesta, descargar = self._descargar(archivo_b.pk, Escenario.sol_a, ESQUEMA_B)

        self.assertEqual(respuesta.status_code, 403, respuesta.content)
        self.assertEqual(respuesta.json()['detail'], MENSAJE_NO_MIEMBRO)
        descargar.assert_not_called()
        self.assertNotIn('secreto_de_b', respuesta.content.decode())
