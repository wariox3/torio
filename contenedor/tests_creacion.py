"""
Creación de contenedores en segundo plano.

`POST /contenedor/cliente/` registra el contenedor en `creando` y encola
`contenedor.tasks.crear_contenedor`, que migra, siembra y lo deja `listo`. El diseño,
en `docs/creacion_contenedor.md`.

Casi todo acá es barato: el request ya no migra, así que los contenedores de prueba
son filas sin schema, o con uno vacío. Solo `TareaCompletaTests` construye un
contenedor de verdad (unos 20 s), y por eso hace todo lo caro en un único test.

Correr solo esto:

    python manage.py test contenedor.tests_creacion
"""

import io
from contextlib import redirect_stdout
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import TestCase
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, schema_exists
from kombu.exceptions import OperationalError
from rest_framework import permissions
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.throttling import ScopedRateThrottle
from tenant_users.permissions.models import UserTenantPermissions

from contenedor import tasks
from contenedor.models import CtnCliente, CtnInvitacion, CtnSuscripcionTipo
from contenedor.views.cliente import SUSCRIPCION_TIPO_PRUEBA_ID, CtnClienteViewSet
from contenedor.views.invitacion import CtnInvitacionViewSet
from general.management.commands.cargar_datos_tenant import Command as CargarDatosTenant
from general.models import GenCiudad, GenContacto
from seguridad.models import CAMPOS_ACCESO, SegUsuario, SegUsuarioCliente


class _ClienteView(CtnClienteViewSet):
    """Sin auth ni throttle: el usuario se inyecta con force_authenticate."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def get_throttles(self):
        return []


class _InvitacionView(CtnInvitacionViewSet):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []


def _tablas_del_schema(schema):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT count(*) FROM information_schema.tables WHERE table_schema = %s',
            [schema],
        )
        return cursor.fetchone()[0]


class CreacionBase(TestCase):
    """
    Todo corre en el schema público, como en producción sin `X-Tenant`: django-tenants
    prohíbe crear un tenant desde dentro de otro.
    """

    def setUp(self):
        connection.set_schema_to_public()
        self.addCleanup(connection.set_schema_to_public)
        self.addCleanup(cache.clear)
        self.factory = APIRequestFactory()
        self.duenio = self._usuario('duenio@ejemplo.com')
        CtnSuscripcionTipo.objects.create(
            id=SUSCRIPCION_TIPO_PRUEBA_ID,
            nombre='Prueba ERP', precio=0, suscripcion_categoria_id=99,
        )

    @staticmethod
    def _usuario(email):
        return SegUsuario.objects.create(email=email, is_active=True, is_verified=True)

    @staticmethod
    def _cliente(schema, owner, estado, miembro=True):
        """Un contenedor registrado sin schema, como lo deja un request a medias."""
        cliente = CtnCliente(
            schema_name=schema, nombre=schema, celular='3000000000',
            correo=f'{schema}@ejemplo.com', owner=owner, estado=estado,
        )
        cliente.auto_create_schema = False
        cliente.save()
        if miembro:
            SegUsuarioCliente.objects.create(usuario=owner, cliente=cliente, propietario=True)
        return cliente

    def _crear(self, schema, usuario=None):
        peticion = self.factory.post('/contenedor/cliente/', {
            'schema_name': schema,
            'nombre': f'Contenedor {schema}',
            'celular': '+573001112233',
            # Fijo: con el nombre del schema, uno inválido haría fallar al correo antes.
            'correo': 'contenedor@ejemplo.com',
        }, format='json')
        force_authenticate(peticion, user=usuario or self.duenio)
        return _ClienteView.as_view({'post': 'create'})(peticion)

    def _accion(self, metodo, accion, cliente, usuario=None):
        peticion = getattr(self.factory, metodo)(f'/contenedor/cliente/{cliente.pk}/{accion}/')
        force_authenticate(peticion, user=usuario or self.duenio)
        return _ClienteView.as_view({metodo: accion})(peticion, pk=cliente.pk)


# --------------------------------------------------------------------------- #
# El request
# --------------------------------------------------------------------------- #

class CrearTests(CreacionBase):

    def test_responde_202_sin_migrar(self):
        """
        El request deja el contenedor en `creando` con su schema vacío: las
        migraciones, que eran las que bloqueaban `seg_usuario`, ya no corren acá.
        """
        respuesta = self._crear('nuevo')

        self.assertEqual(respuesta.status_code, 202, respuesta.data)
        self.assertEqual(respuesta.data['estado'], CtnCliente.ESTADO_CREANDO)
        cliente = CtnCliente.objects.get(schema_name='nuevo')
        self.assertEqual(cliente.estado, CtnCliente.ESTADO_CREANDO)
        self.assertTrue(schema_exists('nuevo'))
        self.assertEqual(_tablas_del_schema('nuevo'), 0)

    def test_la_membresia_del_owner_se_crea_en_el_request(self):
        """Así el contenedor aparece en `lista-usuario` mientras se crea."""
        self._crear('nuevo')

        membresia = SegUsuarioCliente.objects.get(
            usuario=self.duenio, cliente__schema_name='nuevo',
        )
        self.assertTrue(membresia.propietario)
        for campo in CAMPOS_ACCESO:
            self.assertTrue(getattr(membresia, campo), campo)

    def test_la_tarea_se_encola_al_commit(self):
        """Antes del COMMIT el worker no vería ni el contenedor ni su schema."""
        with patch.object(tasks.crear_contenedor, 'delay') as delay:
            with self.captureOnCommitCallbacks() as pendientes:
                self._crear('nuevo')
            delay.assert_not_called()
            for callback in pendientes:
                callback()

        delay.assert_called_once_with(CtnCliente.objects.get(schema_name='nuevo').pk)

    def test_sin_broker_queda_en_error_y_no_en_creando(self):
        """Si quedara en `creando`, no habría forma de reintentarlo por 30 minutos."""
        with patch.object(
            tasks.crear_contenedor, 'delay', side_effect=OperationalError('sin RabbitMQ'),
        ):
            with self.assertLogs('contenedor.tasks', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    respuesta = self._crear('nuevo')

        self.assertEqual(respuesta.status_code, 202)
        self.assertEqual(
            CtnCliente.objects.get(schema_name='nuevo').estado, CtnCliente.ESTADO_ERROR,
        )

    def test_un_nombre_con_comillas_no_llega_al_sql(self):
        """
        `is_valid_schema_name` de django-tenants deja pasar comillas, y el nombre va
        interpolado en `CREATE SCHEMA "<nombre>"`.
        """
        for nombre in ('x"; DROP TABLE seg_usuario; --', 'Mayusculas', 'con-guion', 'pg_algo', '1empieza'):
            with self.subTest(nombre=nombre):
                respuesta = self._crear(nombre)

                self.assertEqual(respuesta.status_code, 400)
                self.assertIn('no es un nombre de schema válido', respuesta.data['detail'])
                self.assertFalse(CtnCliente.objects.filter(schema_name=nombre).exists())

    def test_un_schema_huerfano_no_se_reutiliza(self):
        """Un schema sin CtnCliente trae datos de otro: no se le asigna al nuevo."""
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA huerfano')

        respuesta = self._crear('huerfano')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('ya está registrado', respuesta.data['detail'])

    def test_el_mismo_nombre_a_la_vez_da_400_y_no_500(self):
        """
        Dos POST simultáneos pasan los dos la validación del serializer; al segundo
        lo frena el índice único. Se simula con el INSERT fallando.
        """
        with patch.object(CtnCliente, 'save', side_effect=IntegrityError('duplicado')):
            respuesta = self._crear('nuevo')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('ya está registrado', respuesta.data['detail'])
        self.assertFalse(schema_exists('nuevo'))

    def test_solo_uno_en_creacion_por_usuario(self):
        self.assertEqual(self._crear('primero').status_code, 202)

        respuesta = self._crear('segundo')

        self.assertEqual(respuesta.status_code, 409)
        self.assertFalse(CtnCliente.objects.filter(schema_name='segundo').exists())

    def test_otro_usuario_si_puede_crear_a_la_vez(self):
        self.assertEqual(self._crear('primero').status_code, 202)

        respuesta = self._crear('segundo', usuario=self._usuario('otro@ejemplo.com'))

        self.assertEqual(respuesta.status_code, 202)

    def test_create_lleva_su_propio_throttle(self):
        """Solo `create`: el resto de las acciones se quedan con los límites generales."""
        vista = CtnClienteViewSet()

        vista.action = 'create'
        self.assertTrue(any(isinstance(t, ScopedRateThrottle) for t in vista.get_throttles()))
        self.assertEqual(vista.throttle_scope, 'crear_contenedor')
        self.assertIn('crear_contenedor', ScopedRateThrottle.THROTTLE_RATES)

        vista.action = 'list'
        self.assertFalse(any(isinstance(t, ScopedRateThrottle) for t in vista.get_throttles()))


# --------------------------------------------------------------------------- #
# Estado, reintentar, eliminar, actualizar
# --------------------------------------------------------------------------- #

class EstadoTests(CreacionBase):

    def test_creando_trae_el_paso_de_la_cache(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)
        tasks._anotar_paso(cliente.pk, tasks.PASO_MIGRACIONES)

        respuesta = self._accion('get', 'estado', cliente)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, {'estado': 'creando', 'paso': 'migraciones'})

    def test_sin_cache_el_estado_llega_igual(self):
        """El paso es solo avance: con Redis caído o la clave vencida, llega `None`."""
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        respuesta = self._accion('get', 'estado', cliente)

        self.assertEqual(respuesta.data, {'estado': 'creando', 'paso': None})

    def test_listo_no_trae_paso(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_LISTO)
        tasks._anotar_paso(cliente.pk, tasks.PASO_CATALOGOS)

        respuesta = self._accion('get', 'estado', cliente)

        self.assertEqual(respuesta.data, {'estado': 'listo', 'paso': None})

    def test_un_no_miembro_no_lo_ve(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        respuesta = self._accion('get', 'estado', cliente, usuario=self._usuario('x@ejemplo.com'))

        self.assertEqual(respuesta.status_code, 404)


class ReintentarTests(CreacionBase):

    def _reintentar(self, cliente, usuario=None):
        with patch.object(tasks.crear_contenedor, 'delay') as delay:
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self._accion('post', 'reintentar', cliente, usuario)
        return respuesta, delay

    def test_uno_fallido_vuelve_a_creando_y_se_encola(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_ERROR)

        respuesta, delay = self._reintentar(cliente)

        self.assertEqual(respuesta.status_code, 202, respuesta.data)
        cliente.refresh_from_db()
        self.assertEqual(cliente.estado, CtnCliente.ESTADO_CREANDO)
        delay.assert_called_once_with(cliente.pk)

    def test_uno_atascado_en_creando_se_puede_reintentar(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)
        CtnCliente.objects.filter(pk=cliente.pk).update(
            fecha_creacion=timezone.now() - timedelta(hours=1),
        )

        respuesta, delay = self._reintentar(cliente)

        self.assertEqual(respuesta.status_code, 202, respuesta.data)
        delay.assert_called_once_with(cliente.pk)

    def test_uno_que_se_esta_creando_no_se_reintenta(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        respuesta, delay = self._reintentar(cliente)

        self.assertEqual(respuesta.status_code, 409)
        delay.assert_not_called()

    def test_uno_listo_no_se_reintenta(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_LISTO)

        respuesta, delay = self._reintentar(cliente)

        self.assertEqual(respuesta.status_code, 409)
        delay.assert_not_called()

    def test_solo_el_owner(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_ERROR)
        miembro = self._usuario('miembro@ejemplo.com')
        SegUsuarioCliente.objects.create(usuario=miembro, cliente=cliente)

        respuesta, delay = self._reintentar(cliente, usuario=miembro)

        self.assertEqual(respuesta.status_code, 403)
        delay.assert_not_called()


class EliminarYActualizarTests(CreacionBase):

    def _eliminar(self, cliente, usuario=None):
        peticion = self.factory.delete(f'/contenedor/cliente/{cliente.pk}/')
        force_authenticate(peticion, user=usuario or self.duenio)
        return _ClienteView.as_view({'delete': 'destroy'})(peticion, pk=cliente.pk)

    def test_uno_en_creacion_no_se_elimina(self):
        """Sería tirarle el schema debajo a la tarea."""
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        respuesta = self._eliminar(cliente)

        self.assertEqual(respuesta.status_code, 409)
        self.assertTrue(CtnCliente.objects.filter(pk=cliente.pk).exists())

    def test_el_owner_elimina_uno_fallido_y_su_schema(self):
        """
        Por owner y no por `es_superusuario`: esa consulta lee el schema del tenant,
        que en uno fallido no tiene tablas.
        """
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_ERROR)
        with connection.cursor() as cursor:
            cursor.execute('CREATE SCHEMA nuevo')

        respuesta = self._eliminar(cliente)

        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(CtnCliente.objects.filter(pk=cliente.pk).exists())
        self.assertFalse(schema_exists('nuevo'))

    def test_un_miembro_no_elimina_uno_fallido(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_ERROR)
        miembro = self._usuario('miembro@ejemplo.com')
        SegUsuarioCliente.objects.create(usuario=miembro, cliente=cliente)

        respuesta = self._eliminar(cliente, usuario=miembro)

        self.assertEqual(respuesta.status_code, 403)

    def test_uno_que_no_esta_listo_no_se_actualiza(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)
        peticion = self.factory.patch(
            f'/contenedor/cliente/{cliente.pk}/', {'nombre': 'Otro'}, format='json',
        )
        force_authenticate(peticion, user=self.duenio)

        respuesta = _ClienteView.as_view({'patch': 'partial_update'})(peticion, pk=cliente.pk)

        self.assertEqual(respuesta.status_code, 409)


# --------------------------------------------------------------------------- #
# Lo que recorre contenedores
# --------------------------------------------------------------------------- #

class NoListoFueraDeAlcanceTests(CreacionBase):

    def test_no_se_invita_a_uno_que_no_esta_listo(self):
        """Aceptar escribiría `UserTenantPermissions` en un schema sin tablas."""
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)
        invitado = self._usuario('invitado@ejemplo.com')
        peticion = self.factory.post('/contenedor/invitacion/', {
            'cliente_id': cliente.pk, 'usuario_id': invitado.pk,
        }, format='json')
        force_authenticate(peticion, user=self.duenio)

        respuesta = _InvitacionView.as_view({'post': 'create'})(peticion)

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(CtnInvitacion.objects.filter(cliente=cliente).exists())

    def test_cargar_datos_tenant_sin_schema_se_salta_los_que_no_estan_listos(self):
        """Uno en `creando` lo siembra su tarea; uno en `error` puede no tener tablas."""
        listo = self._cliente('listo', self.duenio, CtnCliente.ESTADO_LISTO)
        self._cliente('creando', self.duenio, CtnCliente.ESTADO_CREANDO, miembro=False)
        self._cliente('fallido', self.duenio, CtnCliente.ESTADO_ERROR, miembro=False)
        visitados = set()

        def anotar(comando, archivo, inicial=False):
            visitados.add(connection.schema_name)

        with patch.object(CargarDatosTenant, '_cargar', anotar):
            call_command('cargar_datos_tenant', stdout=io.StringIO())

        self.assertIn(listo.schema_name, visitados)
        self.assertNotIn('creando', visitados)
        self.assertNotIn('fallido', visitados)


# --------------------------------------------------------------------------- #
# La tarea
# --------------------------------------------------------------------------- #

class TareaTests(CreacionBase):
    """La lógica de reintentos, con `_construir` sustituido: sin migraciones."""

    def test_una_falla_persistente_se_reintenta_y_termina_en_error(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        with patch.object(tasks, '_construir', side_effect=RuntimeError('sin disco')) as construir:
            with self.assertLogs('contenedor.tasks', level='ERROR') as registro:
                tasks.crear_contenedor.apply(args=[cliente.pk])

        # El intento original más los reintentos.
        self.assertEqual(construir.call_count, tasks.MAXIMO_REINTENTOS + 1)
        self.assertIn('sin disco', '\n'.join(registro.output))
        cliente.refresh_from_db()
        self.assertEqual(cliente.estado, CtnCliente.ESTADO_ERROR)

    def test_una_falla_pasajera_se_recupera_en_el_reintento(self):
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        with patch.object(tasks, '_construir', side_effect=[RuntimeError('corte'), None]) as construir:
            tasks.crear_contenedor.apply(args=[cliente.pk])

        self.assertEqual(construir.call_count, 2)
        cliente.refresh_from_db()
        self.assertEqual(cliente.estado, CtnCliente.ESTADO_LISTO)

    def test_una_entrega_repetida_no_hace_nada(self):
        """`acks_late`, o un reintento doble de uno atascado: ya está listo o falló."""
        for estado in (CtnCliente.ESTADO_LISTO, CtnCliente.ESTADO_ERROR):
            with self.subTest(estado=estado):
                cliente = self._cliente(f'c_{estado}', self.duenio, estado, miembro=False)

                with patch.object(tasks, '_construir') as construir:
                    tasks.crear_contenedor.apply(args=[cliente.pk])

                construir.assert_not_called()
                cliente.refresh_from_db()
                self.assertEqual(cliente.estado, estado)

    def test_si_otra_ejecucion_lo_esta_construyendo_no_hace_nada(self):
        """
        El worker tiene dos procesos: un reintento doble o una re-entrega pueden
        coincidir con la ejecución en curso, y dos a la vez migrarían el mismo schema.
        """
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        with tasks._candado(cliente.pk) as tomado:
            self.assertTrue(tomado)
            with patch.object(tasks, '_construir') as construir:
                tasks.crear_contenedor.apply(args=[cliente.pk])

        construir.assert_not_called()
        cliente.refresh_from_db()
        self.assertEqual(cliente.estado, CtnCliente.ESTADO_CREANDO)

    def test_el_candado_se_suelta_al_terminar(self):
        """Incluso si la construcción falla: si no, el reintento lo encontraría tomado."""
        cliente = self._cliente('nuevo', self.duenio, CtnCliente.ESTADO_CREANDO)

        with patch.object(tasks, '_construir', side_effect=RuntimeError('corte')):
            with self.assertLogs('contenedor.tasks', level='ERROR'):
                tasks.crear_contenedor.apply(args=[cliente.pk])

        with tasks._candado(cliente.pk) as tomado:
            self.assertTrue(tomado)

    def test_un_contenedor_borrado_no_hace_nada(self):
        with patch.object(tasks, '_construir') as construir:
            tasks.crear_contenedor.apply(args=[999999])

        construir.assert_not_called()


class TareaCompletaTests(CreacionBase):
    """
    Un contenedor construido de verdad: schema, 126 migraciones, permisos y
    catálogos. Es lo caro del módulo, así que va en un solo test.
    """

    def test_construye_el_contenedor_y_repetirla_no_duplica_nada(self):
        self._crear('completo')
        cliente = CtnCliente.objects.get(schema_name='completo')

        # `migrate_schemas` escribe en stdout aunque se le pase verbosity=0.
        with redirect_stdout(io.StringIO()):
            tasks.crear_contenedor.apply(args=[cliente.pk])

        cliente.refresh_from_db()
        self.assertEqual(cliente.estado, CtnCliente.ESTADO_LISTO)
        with schema_context('completo'):
            permisos = UserTenantPermissions.objects.get(profile=self.duenio)
            self.assertTrue(permisos.is_superuser)
            self.assertTrue(GenCiudad.objects.exists())
            # La semilla depende por FK de los catálogos: si el orden se rompiera,
            # esta fila no existiría.
            self.assertTrue(GenContacto.objects.filter(pk=1).exists())
            ciudades = GenCiudad.objects.count()
        with schema_context(get_public_schema_name()):
            self.assertEqual(cache.get(tasks.clave_paso(cliente.pk)), tasks.PASO_CATALOGOS)

        # Una segunda entrega sobre el mismo schema —el worker murió después de
        # construirlo y antes de confirmar— retoma y termina sin duplicar nada.
        CtnCliente.objects.filter(pk=cliente.pk).update(estado=CtnCliente.ESTADO_CREANDO)
        with redirect_stdout(io.StringIO()):
            tasks.crear_contenedor.apply(args=[cliente.pk])

        cliente.refresh_from_db()
        self.assertEqual(cliente.estado, CtnCliente.ESTADO_LISTO)
        with schema_context('completo'):
            self.assertEqual(UserTenantPermissions.objects.filter(profile=self.duenio).count(), 1)
            self.assertEqual(GenCiudad.objects.count(), ciudades)
