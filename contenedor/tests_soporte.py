"""
Soporte del staff: `POST /contenedor/cliente/<id>/soporte/`.

Abrir soporte escribe `UserTenantPermissions` dentro del schema del contenedor y
después se entra con `X-Tenant`, así que hace falta un contenedor real, con su
schema migrado. Se crea una sola vez para el módulo (`setUpModule`), igual que en
`tests_aislamiento.py`: cada `TestCase` revierte lo suyo y el escenario se comparte.

Lo que no necesita schema (panel, imagen, ingresar…) está en `tests_master.py`.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework_simplejwt.tokens import RefreshToken
from tenant_users.permissions.models import UserTenantPermissions

from contenedor.models import CtnCliente, CtnDominio, CtnSuscripcion, CtnSuscripcionTipo
from seguridad.models import CAMPOS_ACCESO, SegMfaUsuario, SegUsuario, SegUsuarioCliente

ESQUEMA = 'soporte_staff'
RUTA_ITEM = '/general/item/'


class Escenario:
    cliente = None
    owner = None
    staff = None
    staff_sin_mfa = None
    tipo = None


def _usuario(email, staff=False, mfa=False):
    """
    Idempotente: con `--keepdb` el usuario sobrevive de una corrida a otra, y
    borrarlo al final no se puede (su FK llega a tablas de tenant que el público no tiene).
    """
    usuario, _ = SegUsuario.objects.get_or_create(
        email=email, defaults={'is_active': True, 'is_verified': True},
    )
    if staff:
        UserTenantPermissions.objects.update_or_create(profile=usuario, defaults={'is_staff': True})
    if mfa:
        SegMfaUsuario.objects.update_or_create(
            usuario=usuario, defaults={'metodo': 'correo', 'activo': True, 'fecha_activacion': timezone.now()},
        )
    return usuario


def setUpModule():
    from general.signals import limpiar_caches

    limpiar_caches()
    with schema_context(get_public_schema_name()):
        Escenario.owner = _usuario('owner.soporte@ejemplo.com')
        Escenario.staff = _usuario('staff.soporte@ejemplo.com', staff=True, mfa=True)
        Escenario.staff_sin_mfa = _usuario('staff.sinmfa@ejemplo.com', staff=True)
        Escenario.tipo, _ = CtnSuscripcionTipo.objects.get_or_create(
            id=96, defaults={'nombre': 'Plan soporte', 'precio': 0, 'suscripcion_categoria_id': 96},
        )

        cliente = CtnCliente(
            schema_name=ESQUEMA, nombre='Contenedor soporte', celular='+573000000000',
            correo='soporte@ejemplo.com', owner=Escenario.owner,
        )
        cliente.save(verbosity=0)
        CtnDominio.objects.create(tenant=cliente, domain='soporte.torio.test', is_primary=True)
        hoy = timezone.localdate()
        suscripcion = CtnSuscripcion.objects.create(
            cliente=cliente, usuario=Escenario.owner, suscripcion_tipo=Escenario.tipo,
            fecha_inicio=hoy - timedelta(days=1), fecha_fin=hoy + timedelta(days=30),
            frecuencia=CtnSuscripcion.FRECUENCIA_PRUEBA,
        )
        CtnCliente.objects.filter(pk=cliente.pk).update(suscripcion=suscripcion)
        cliente.refresh_from_db()
        cliente.add_user(
            Escenario.owner, propietario=True, is_superuser=True,
            accesos=dict.fromkeys(CAMPOS_ACCESO, True),
        )
        Escenario.cliente = cliente


def tearDownModule():
    from general.signals import limpiar_caches

    with schema_context(get_public_schema_name()):
        if Escenario.cliente is not None:
            SegUsuarioCliente.objects.filter(cliente=Escenario.cliente).delete()
            CtnCliente.objects.filter(pk=Escenario.cliente.pk).update(suscripcion=None)
            CtnSuscripcion.objects.filter(cliente=Escenario.cliente).delete()
            CtnDominio.objects.filter(tenant=Escenario.cliente).delete()
            Escenario.cliente.delete(force_drop=True)
    limpiar_caches()


class SoporteTests(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(connection.set_schema_to_public)
        self.cliente = Escenario.cliente
        self.ruta = f'/contenedor/cliente/{self.cliente.id}/soporte/'

    @staticmethod
    def _headers(usuario, tenant=None):
        cabeceras = {'authorization': f'Bearer {RefreshToken.for_user(usuario).access_token}'}
        if tenant:
            cabeceras['x-tenant'] = tenant
        return {'headers': cabeceras}

    def _abrir(self, usuario=None, ruta=None):
        return self.client.post(ruta or self.ruta, **self._headers(usuario or Escenario.staff))

    def _membresia(self):
        return SegUsuarioCliente.objects.get(usuario=Escenario.staff, cliente=self.cliente)

    def _item(self, usuario):
        return self.client.get(RUTA_ITEM, **self._headers(usuario, ESQUEMA))

    # ---- quién puede abrirlo ----

    def test_no_staff_403(self):
        self.assertEqual(self._abrir(Escenario.owner).status_code, 403)

    def test_staff_sin_mfa_403(self):
        respuesta = self._abrir(Escenario.staff_sin_mfa)

        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('MFA', respuesta.json()['detail'])
        self.assertFalse(SegUsuarioCliente.objects.filter(usuario=Escenario.staff_sin_mfa).exists())

    def test_inexistente_o_publico_404(self):
        publico = CtnCliente(
            schema_name=get_public_schema_name(), nombre='Público', celular='+573000000000',
            correo='publico@ejemplo.com',
        )
        publico.auto_create_schema = False
        publico.save()

        for cliente_id in (999999, publico.id):
            with self.subTest(cliente_id=cliente_id):
                respuesta = self._abrir(ruta=f'/contenedor/cliente/{cliente_id}/soporte/')
                self.assertEqual(respuesta.status_code, 404)

    def test_no_listo_409(self):
        creando = CtnCliente(
            schema_name='soporte_creando', nombre='Creando', celular='+573000000000',
            correo='creando@ejemplo.com', estado=CtnCliente.ESTADO_CREANDO,
        )
        creando.auto_create_schema = False
        creando.save()

        respuesta = self._abrir(ruta=f'/contenedor/cliente/{creando.id}/soporte/')

        self.assertEqual(respuesta.status_code, 409)

    # ---- abrirlo ----

    def test_crea_la_membresia_de_soporte_con_todo(self):
        respuesta = self._abrir()

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        datos = respuesta.json()
        self.assertIs(datos['soporte'], True)
        self.assertIs(datos['propietario'], False)
        self.assertEqual(datos['cliente_id'], self.cliente.id)
        for campo in CAMPOS_ACCESO:
            self.assertIs(datos[campo], True, campo)
        membresia = self._membresia()
        self.assertEqual(datos['id'], membresia.id)
        self.assertTrue(membresia.soporte)
        with schema_context(ESQUEMA):
            permisos = UserTenantPermissions.objects.get(profile=Escenario.staff)
            self.assertTrue(permisos.is_superuser)

    def test_ya_miembro_409(self):
        self._abrir()

        respuesta = self._abrir()

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(SegUsuarioCliente.objects.filter(usuario=Escenario.staff).count(), 1)

    def test_entra_con_x_tenant_y_pasa_los_permisos_de_modelo(self):
        self.assertEqual(self._item(Escenario.staff).status_code, 403)

        self._abrir()

        self.assertEqual(self._item(Escenario.staff).status_code, 200)

    def test_entra_aunque_la_suscripcion_este_vencida(self):
        self._abrir()
        CtnSuscripcion.objects.filter(pk=self.cliente.suscripcion_id).update(
            fecha_fin=timezone.localdate() - timedelta(days=1),
        )

        del_owner = self._item(Escenario.owner)

        self.assertEqual(self._item(Escenario.staff).status_code, 200)
        self.assertEqual(del_owner.status_code, 403)
        self.assertEqual(del_owner.json()['codigo'], 'suscripcion_vencida')

    # ---- lo que no puede ----

    def test_no_modifica_ni_elimina_el_contenedor(self):
        self._abrir()
        ruta = f'/contenedor/cliente/{self.cliente.id}/'

        self.assertFalse(self.cliente.es_superusuario(Escenario.staff))
        editar = self.client.patch(
            ruta, {'nombre': 'Hackeado'}, content_type='application/json', **self._headers(Escenario.staff),
        )
        eliminar = self.client.delete(ruta, **self._headers(Escenario.staff))

        self.assertEqual((editar.status_code, eliminar.status_code), (403, 403))
        self.assertTrue(CtnCliente.objects.filter(pk=self.cliente.pk, nombre='Contenedor soporte').exists())

    def test_el_owner_no_le_edita_los_accesos(self):
        membresia_id = self._abrir().json()['id']

        respuesta = self.client.patch(
            f'/seguridad/usuario-cliente/{membresia_id}/', {'acceso_venta': False},
            content_type='application/json', **self._headers(Escenario.owner),
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertTrue(self._membresia().acceso_venta)

    # ---- cerrarlo ----

    def test_el_owner_lo_saca(self):
        membresia_id = self._abrir().json()['id']

        respuesta = self.client.delete(
            f'/seguridad/usuario-cliente/{membresia_id}/', **self._headers(Escenario.owner),
        )

        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(SegUsuarioCliente.objects.filter(pk=membresia_id).exists())
        with schema_context(ESQUEMA):
            self.assertFalse(UserTenantPermissions.objects.filter(profile=Escenario.staff).exists())
        self.assertEqual(self._item(Escenario.staff).status_code, 403)

    def test_el_staff_se_sale(self):
        membresia_id = self._abrir().json()['id']

        respuesta = self.client.delete(
            f'/seguridad/usuario-cliente/{membresia_id}/', **self._headers(Escenario.staff),
        )

        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(SegUsuarioCliente.objects.filter(pk=membresia_id).exists())

    # ---- cómo se ve ----

    def test_el_panel_no_lo_cuenta_y_muestra_el_soporte_de_quien_consulta(self):
        membresia_id = self._abrir().json()['id']

        def fila(usuario):
            respuesta = self.client.get(
                '/contenedor/cliente/administrar/', {'nombre': ESQUEMA}, **self._headers(usuario),
            )
            self.assertEqual(respuesta.status_code, 200)
            [resultado] = respuesta.json()['results']
            return resultado

        del_staff = fila(Escenario.staff)
        self.assertEqual(del_staff['usuarios'], 1)  # solo el owner
        self.assertEqual(del_staff['soporte_id'], membresia_id)
        self.assertIsNone(fila(Escenario.staff_sin_mfa)['soporte_id'])

    def test_aparece_en_sus_listas_marcado_como_soporte(self):
        self._abrir()

        propias = self.client.get('/contenedor/cliente/lista-usuario/', **self._headers(Escenario.staff))
        miembros = self.client.get(
            '/seguridad/usuario-cliente/lista-cliente/', {'cliente_id': self.cliente.id},
            **self._headers(Escenario.owner),
        )

        [propia] = propias.json()['results']
        self.assertIs(propia['soporte'], True)
        por_usuario = {fila['usuario_id']: fila for fila in miembros.json()['results']}
        self.assertIs(por_usuario[Escenario.staff.id]['soporte'], True)
        self.assertIs(por_usuario[Escenario.owner.id]['soporte'], False)
