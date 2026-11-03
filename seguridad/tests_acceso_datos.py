"""
Quién ve y quién modifica los datos de cuentas y suscripciones (público, sin `X-Tenant`).

- `/seguridad/usuario/`: el CRUD es solo de la propia cuenta. Antes cualquier sesión
  listaba a todos los usuarios y podía editar o borrar cuentas ajenas.
- `/contenedor/suscripcion/`: se ven las de los contenedores de los que se es miembro
  (el staff, todas); crear, editar y borrar es solo del staff. Antes cualquier sesión
  podía alargar su `fecha_fin` con un PATCH.

No hace falta schema de tenant: los contenedores se guardan sin crearlo.
"""

from datetime import date

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from tenant_users.permissions.models import UserTenantPermissions

from contenedor.models import CtnCliente, CtnSuscripcion, CtnSuscripcionTipo
from seguridad.models import SegUsuario, SegUsuarioCliente


def _usuario(email, staff=False):
    usuario = SegUsuario.objects.create(email=email, is_active=True, is_verified=True)
    if staff:
        UserTenantPermissions.objects.create(profile=usuario, is_staff=True)
    return usuario


def _cliente(schema, owner):
    cliente = CtnCliente(
        schema_name=schema, nombre=schema, celular='+573000000000', correo=f'{schema}@ejemplo.com',
        owner=owner,
    )
    cliente.auto_create_schema = False
    cliente.save()
    return cliente


class UsuarioPropioTests(TestCase):

    def setUp(self):
        cache.clear()
        self.yo = _usuario('yo@ejemplo.com')
        self.otro = _usuario('otro@ejemplo.com')
        self.client = APIClient()
        # Instancia nueva: `is_staff` se cachea en el usuario.
        self.client.force_authenticate(SegUsuario.objects.get(pk=self.yo.pk))

    def test_la_lista_solo_trae_la_propia_cuenta(self):
        respuesta = self.client.get('/seguridad/usuario/')

        self.assertEqual(respuesta.status_code, 200)
        filas = respuesta.data['results'] if isinstance(respuesta.data, dict) else respuesta.data
        self.assertEqual([fila['id'] for fila in filas], [self.yo.id])

    def test_una_cuenta_ajena_no_se_ve_ni_se_toca(self):
        ruta = f'/seguridad/usuario/{self.otro.pk}/'

        self.assertEqual(self.client.get(ruta).status_code, 404)
        self.assertEqual(self.client.patch(ruta, {'nombre_corto': 'Hackeado'}).status_code, 404)
        self.assertEqual(self.client.put(ruta, {'nombre_corto': 'Hackeado'}).status_code, 404)
        self.assertEqual(self.client.delete(ruta).status_code, 404)

        self.otro.refresh_from_db()
        self.assertNotEqual(self.otro.nombre_corto, 'Hackeado')

    def test_la_propia_si(self):
        ruta = f'/seguridad/usuario/{self.yo.pk}/'

        self.assertEqual(self.client.get(ruta).status_code, 200)
        self.assertEqual(self.client.patch(ruta, {'nombre_corto': 'Nuevo'}).status_code, 200)
        self.yo.refresh_from_db()
        self.assertEqual(self.yo.nombre_corto, 'Nuevo')

    def test_seleccionar_sigue_buscando_entre_todos(self):
        """Es el buscador para invitar: id, nombre y correo, nada más."""
        respuesta = self.client.get('/seguridad/usuario/seleccionar/', {'search': 'otro@'})

        self.assertEqual(respuesta.status_code, 200)
        [fila] = respuesta.data['results']
        self.assertEqual(set(fila), {'id', 'nombre_corto', 'email'})

    def test_anonimo_401(self):
        self.assertEqual(APIClient().get('/seguridad/usuario/').status_code, 401)


class SuscripcionAccesoTests(TestCase):

    def setUp(self):
        cache.clear()
        self.miembro = _usuario('miembro.sus@ejemplo.com')
        self.extranio = _usuario('extranio.sus@ejemplo.com')
        self.staff = _usuario('staff.sus@ejemplo.com', staff=True)
        tipo = CtnSuscripcionTipo.objects.create(
            id=93, nombre='Plan acceso', precio=0, suscripcion_categoria_id=93,
        )
        self.propio = _cliente('sus_propio', self.miembro)
        self.ajeno = _cliente('sus_ajeno', self.extranio)
        SegUsuarioCliente.objects.create(usuario=self.miembro, cliente=self.propio, propietario=True)
        SegUsuarioCliente.objects.create(usuario=self.extranio, cliente=self.ajeno, propietario=True)
        datos = {'suscripcion_tipo': tipo, 'fecha_inicio': date(2026, 1, 1), 'fecha_fin': date(2026, 2, 1)}
        self.sus_propia = CtnSuscripcion.objects.create(cliente=self.propio, usuario=self.miembro, **datos)
        self.sus_ajena = CtnSuscripcion.objects.create(cliente=self.ajeno, usuario=self.extranio, **datos)

    def _cliente_api(self, usuario):
        api = APIClient()
        api.force_authenticate(SegUsuario.objects.get(pk=usuario.pk))
        return api

    @staticmethod
    def _ids(respuesta):
        filas = respuesta.data['results'] if isinstance(respuesta.data, dict) else respuesta.data
        return {fila['id'] for fila in filas}

    def test_el_miembro_solo_ve_las_de_sus_contenedores(self):
        api = self._cliente_api(self.miembro)

        self.assertEqual(self._ids(api.get('/contenedor/suscripcion/')), {self.sus_propia.id})
        self.assertEqual(self._ids(api.get('/contenedor/suscripcion/', {'cliente_id': self.ajeno.id})), set())
        self.assertEqual(api.get(f'/contenedor/suscripcion/{self.sus_ajena.id}/').status_code, 404)
        self.assertEqual(api.get(f'/contenedor/suscripcion/{self.sus_propia.id}/').status_code, 200)

    def test_el_miembro_no_la_modifica_ni_la_borra_ni_crea(self):
        api = self._cliente_api(self.miembro)
        ruta = f'/contenedor/suscripcion/{self.sus_propia.id}/'

        self.assertEqual(api.patch(ruta, {'fecha_fin': '2099-01-01'}, format='json').status_code, 403)
        self.assertEqual(api.delete(ruta).status_code, 403)
        self.assertEqual(api.post('/contenedor/suscripcion/', {}, format='json').status_code, 403)

        self.sus_propia.refresh_from_db()
        self.assertEqual(self.sus_propia.fecha_fin, date(2026, 2, 1))

    def test_el_staff_ve_todas_y_las_modifica(self):
        api = self._cliente_api(self.staff)

        self.assertEqual(self._ids(api.get('/contenedor/suscripcion/')), {self.sus_propia.id, self.sus_ajena.id})
        respuesta = api.patch(
            f'/contenedor/suscripcion/{self.sus_ajena.id}/', {'fecha_fin': '2026-03-01'}, format='json',
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.sus_ajena.refresh_from_db()
        self.assertEqual(self.sus_ajena.fecha_fin, date(2026, 3, 1))
