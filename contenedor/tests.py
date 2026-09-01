"""
Pruebas del flag `propietario` de `SegUsuarioCliente`.

Reemplazó al FK `rol` y no hay más fuente de verdad por membresía sobre quién es
dueño del contenedor, así que se cubren los dos caminos que crean membresías:
crear un contenedor (marca al dueño) y aceptar una invitación (no lo marca).
"""

import io
from contextlib import redirect_stdout

from django.contrib.auth.models import Group
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context
from rest_framework import permissions
from rest_framework.test import APIRequestFactory, force_authenticate

from contenedor.models import CtnCliente, CtnInvitacion, CtnSuscripcion, CtnSuscripcionTipo
from contenedor.views.cliente import DIAS_PRUEBA, SUSCRIPCION_TIPO_PRUEBA_ID, CtnClienteViewSet
from contenedor.views.invitacion import CtnInvitacionViewSet
from seguridad.models import CAMPOS_ACCESO, SegUsuario, SegUsuarioCliente


class _ClienteViewSinPermisos(CtnClienteViewSet):
    """Variante sin auth/throttle: el usuario se inyecta con force_authenticate."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class _InvitacionViewSinPermisos(CtnInvitacionViewSet):
    """Variante sin auth/throttle: el usuario se inyecta con force_authenticate."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


class PropietarioTests(TenantTestCase):
    """
    `TenantTestCase` crea un schema de tenant real, que es lo que necesita
    `CtnCliente.add_user`: está decorado con `@schema_required` y escribe el
    `UserTenantPermissions` dentro del schema del contenedor.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Contenedor de prueba'
        tenant.celular = '3000000000'
        tenant.correo = 'contenedor@ejemplo.com'
        return tenant

    def setUp(self):
        self.factory = APIRequestFactory()
        self.addCleanup(self._limpiar_caches_auditoria)

        # Se crean por el modelo y no con `create_user`: el manager de
        # django-tenant-users exige estar en el schema público y además vincula
        # al usuario con el tenant público, que en pruebas no existe. Acá solo
        # hace falta la fila de usuario; la sesión la inyecta force_authenticate.
        self.duenio = SegUsuario.objects.create(
            email='duenio@ejemplo.com', is_active=True, is_verified=True,
        )
        self.invitado = SegUsuario.objects.create(
            email='invitado@ejemplo.com', is_active=True, is_verified=True,
        )

        # `create` fija este id: es el plan de prueba con el que arranca todo
        # contenedor nuevo, y en producción lo carga `cargar_geodata`.
        self.tipo = CtnSuscripcionTipo.objects.create(
            id=SUSCRIPCION_TIPO_PRUEBA_ID,
            nombre='Prueba ERP', precio=0, suscripcion_categoria_id=99,
        )

    @staticmethod
    def _limpiar_caches_auditoria():
        """
        `general.signals` cachea los ids de GenAccion/GenModelo por schema, pero
        los schemas de prueba se crean y destruyen dentro del mismo proceso: una
        entrada sobreviviría al schema que la originó y otro test podría reusar
        su nombre con ids distintos.
        """
        from general.signals import limpiar_caches

        limpiar_caches()

    # ── Crear contenedor ────────────────────────────────────────────────────

    def test_crear_contenedor_marca_propietario(self):
        """Quien crea el contenedor queda con propietario=True y todos los accesos."""
        peticion = self.factory.post('/contenedor/cliente/', {
            'schema_name': 'nuevo',
            'nombre': 'Contenedor nuevo',
            'celular': '+573001112233',
            'correo': 'nuevo@ejemplo.com',
        }, format='json')
        force_authenticate(peticion, user=self.duenio)

        # `/contenedor/cliente/` es ruta del schema público, y django-tenants
        # prohíbe crear un tenant desde dentro de otro. En producción lo resuelve
        # TenantHeaderMiddleware, que sin header X-Tenant fija el schema público.
        #
        # El redirect_stdout traga el volcado de `cargar_datos_tenant`, que
        # escribe una línea por fixture aunque la vista lo llame con verbosity=0.
        with schema_context(get_public_schema_name()), redirect_stdout(io.StringIO()):
            respuesta = _ClienteViewSinPermisos.as_view({'post': 'create'})(peticion)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)

        cliente = CtnCliente.objects.get(schema_name='nuevo')
        membresia = SegUsuarioCliente.objects.get(usuario=self.duenio, cliente=cliente)

        self.assertTrue(membresia.propietario)
        # El dueño ve todos los módulos: si los accesos quedaran en su default
        # (False) entraría a su propio contenedor con el menú vacío.
        for campo in CAMPOS_ACCESO:
            self.assertTrue(getattr(membresia, campo), campo)

    def test_el_contenedor_nuevo_arranca_en_la_suscripcion_de_prueba(self):
        """
        El plan salió del payload de `create`: quien crea el contenedor ya no elige
        tipo ni frecuencia, así que ambos tienen que quedar fijados por el servidor.
        """
        peticion = self.factory.post('/contenedor/cliente/', {
            'schema_name': 'prueba',
            'nombre': 'Contenedor de prueba',
            'celular': '+573001112233',
            'correo': 'prueba@ejemplo.com',
            # Mandar un plan distinto no cambia nada: ya no es parte del contrato.
            'suscripcion_tipo_id': 1,
            'frecuencia': CtnSuscripcion.FRECUENCIA_ANUAL,
        }, format='json')
        force_authenticate(peticion, user=self.duenio)

        with schema_context(get_public_schema_name()), redirect_stdout(io.StringIO()):
            respuesta = _ClienteViewSinPermisos.as_view({'post': 'create'})(peticion)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)

        cliente = CtnCliente.objects.get(schema_name='prueba')
        suscripcion = cliente.suscripcion

        self.assertEqual(suscripcion.suscripcion_tipo_id, SUSCRIPCION_TIPO_PRUEBA_ID)
        self.assertEqual(suscripcion.frecuencia, CtnSuscripcion.FRECUENCIA_PRUEBA)
        self.assertEqual(
            (suscripcion.fecha_fin - suscripcion.fecha_inicio).days, DIAS_PRUEBA,
        )

    # ── Aceptar invitación ──────────────────────────────────────────────────

    def test_aceptar_invitacion_no_marca_propietario(self):
        """El invitado nunca es dueño, y sus accesos son los de la invitación."""
        grupo = Group.objects.create(name='Grupo de prueba')
        invitacion = CtnInvitacion.objects.create(
            cliente=self.tenant,
            usuario=self.duenio,
            usuario_invitado=self.invitado,
            estado=CtnInvitacion.ESTADO_PENDIENTE,
            acceso_venta=True,
            acceso_inventario=True,
        )
        invitacion.grupos.set([grupo])

        peticion = self.factory.post(f'/contenedor/invitacion/{invitacion.pk}/aceptar/')
        force_authenticate(peticion, user=self.invitado)

        respuesta = _InvitacionViewSinPermisos.as_view({'post': 'aceptar'})(
            peticion, pk=invitacion.pk,
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)

        membresia = SegUsuarioCliente.objects.get(usuario=self.invitado, cliente=self.tenant)

        self.assertFalse(membresia.propietario)
        # Los accesos se copian tal cual: los dos concedidos y el resto en False.
        self.assertTrue(membresia.acceso_venta)
        self.assertTrue(membresia.acceso_inventario)
        for campo in CAMPOS_ACCESO:
            if campo not in ('acceso_venta', 'acceso_inventario'):
                self.assertFalse(getattr(membresia, campo), campo)

    def test_aceptar_invitacion_sin_accesos_deja_todo_en_false(self):
        """Invitar sin pasar accesos deja la membresía sin ningún módulo visible."""
        invitacion = CtnInvitacion.objects.create(
            cliente=self.tenant,
            usuario=self.duenio,
            usuario_invitado=self.invitado,
            estado=CtnInvitacion.ESTADO_PENDIENTE,
        )

        peticion = self.factory.post(f'/contenedor/invitacion/{invitacion.pk}/aceptar/')
        force_authenticate(peticion, user=self.invitado)

        respuesta = _InvitacionViewSinPermisos.as_view({'post': 'aceptar'})(
            peticion, pk=invitacion.pk,
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.data)

        membresia = SegUsuarioCliente.objects.get(usuario=self.invitado, cliente=self.tenant)

        self.assertFalse(membresia.propietario)
        for campo in CAMPOS_ACCESO:
            self.assertFalse(getattr(membresia, campo), campo)
