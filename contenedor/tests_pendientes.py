"""
Pendientes por módulo (`docs/pendientes.md`): el detector de periodos y el comando
`analizar_pendientes`. Lo que ve cada usuario por `GET /contenedor/pendiente/` está en
`seguridad/tests_permisos.py`, junto al resto de la autorización.

`TenantTestCase` da un contenedor con su schema migrado, que es lo que necesitan el
detector (lee `ConPeriodo`) y el comando (entra al schema).
"""

import io
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, schema_context

from contabilidad.models import ConPeriodo
from contabilidad.servicios.pendiente import periodo_anterior_abierto
from contenedor.management.commands import analizar_pendientes
from contenedor.models import CtnCliente, CtnPendiente, CtnPendienteTipo, CtnSuscripcion, CtnSuscripcionTipo

HOY = date(2026, 11, 15)


def _periodo(anio, mes, cerrado=False):
    return ConPeriodo.objects.create(anio=anio, mes=mes, estado_cerrado=cerrado)


class PeriodoAnteriorAbiertoTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test pendientes'
        tenant.celular = '0'
        tenant.correo = 'pendientes@test.com'

    def test_sin_periodos_no_hay_pendiente(self):
        self.assertIsNone(periodo_anterior_abierto(HOY))

    def test_cuenta_solo_los_abiertos_de_meses_anteriores(self):
        _periodo(2026, 10)                 # anterior, abierto → cuenta
        _periodo(2026, 9, cerrado=True)    # anterior, cerrado → no
        _periodo(2026, 11)                 # el actual → no
        _periodo(2026, 12)                 # futuro → no
        _periodo(2026, 13)                 # cierre del año en curso → no, se cierra el año siguiente
        _periodo(2025, 13)                 # cierre del año pasado, abierto → cuenta

        self.assertEqual(periodo_anterior_abierto(HOY), (2, 'Hay 2 periodos anteriores abiertos'))

    def test_singular(self):
        _periodo(2026, 1)

        self.assertEqual(periodo_anterior_abierto(HOY), (1, 'Hay 1 periodo anterior abierto'))

    def test_todos_cerrados_no_hay_pendiente(self):
        _periodo(2026, 1, cerrado=True)

        self.assertIsNone(periodo_anterior_abierto(HOY))


class AnalizarPendientesTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test analizar'
        tenant.celular = '0'
        tenant.correo = 'analizar@test.com'

    def setUp(self):
        hoy = timezone.localdate()
        # El mes anterior a hoy, para que el periodo cuente sin fijar la fecha: el
        # comando siempre usa la de hoy.
        self.anterior = hoy.replace(day=1) - timedelta(days=1)
        with schema_context(get_public_schema_name()):
            grupo = Group.objects.create(name='prueba_contabilidad')
            self.tipo = CtnPendienteTipo.objects.create(id=1, nombre='Periodo anterior abierto', grupo=grupo)
            plan = CtnSuscripcionTipo.objects.create(
                id=94, nombre='Plan pendientes', precio=0, suscripcion_categoria_id=94,
            )
            self.suscripcion = CtnSuscripcion.objects.create(
                cliente=self.tenant, usuario_id=self._usuario_id(), suscripcion_tipo=plan,
                fecha_inicio=hoy - timedelta(days=1), fecha_fin=hoy + timedelta(days=30),
            )
            CtnCliente.objects.filter(pk=self.tenant.pk).update(suscripcion=self.suscripcion)

    @staticmethod
    def _usuario_id():
        from seguridad.models import SegUsuario

        usuario, _ = SegUsuario.objects.get_or_create(
            email='analizar@ejemplo.com', defaults={'is_active': True, 'is_verified': True},
        )
        return usuario.id

    def _analizar(self):
        salida = io.StringIO()
        call_command('analizar_pendientes', schema=self.tenant.schema_name, stdout=salida)
        return salida.getvalue()

    def _pendientes(self):
        with schema_context(get_public_schema_name()):
            return list(CtnPendiente.objects.filter(cliente=self.tenant).values_list(
                'pendiente_tipo_id', 'cantidad', 'mensaje',
            ))

    def test_crea_el_pendiente_del_contenedor(self):
        _periodo(self.anterior.year, self.anterior.month)

        salida = self._analizar()

        self.assertEqual(self._pendientes(), [(1, 1, 'Hay 1 periodo anterior abierto')])
        self.assertIn('Analizados: 1, pendientes: 1, con error: 0', salida)

    def test_cada_corrida_reemplaza_lo_anterior(self):
        _periodo(self.anterior.year, self.anterior.month)
        self._analizar()

        _periodo(self.anterior.year - 1, 13)
        self._analizar()
        self.assertEqual(self._pendientes(), [(1, 2, 'Hay 2 periodos anteriores abiertos')])

        ConPeriodo.objects.update(estado_cerrado=True)
        self._analizar()
        self.assertEqual(self._pendientes(), [])

    def test_si_un_detector_falla_conserva_lo_anterior(self):
        _periodo(self.anterior.year, self.anterior.month)
        self._analizar()

        def roto(hoy):
            raise RuntimeError('detector roto')

        with mock.patch.dict(analizar_pendientes.DETECTORES, {1: roto}), \
                self.assertLogs('contenedor.management.commands.analizar_pendientes', 'ERROR'):
            salida = self._analizar()

        self.assertEqual(self._pendientes(), [(1, 1, 'Hay 1 periodo anterior abierto')])
        self.assertIn('con error: 1', salida)
        self.assertIn(self.tenant.schema_name, salida)

    def test_no_analiza_un_contenedor_vencido(self):
        _periodo(self.anterior.year, self.anterior.month)
        with schema_context(get_public_schema_name()):
            CtnSuscripcion.objects.filter(pk=self.suscripcion.pk).update(
                fecha_fin=timezone.localdate() - timedelta(days=1),
            )

        salida = self._analizar()

        self.assertEqual(self._pendientes(), [])
        self.assertIn('Analizados: 0', salida)

    def test_la_suscripcion_que_vence_hoy_sigue_vigente(self):
        _periodo(self.anterior.year, self.anterior.month)
        with schema_context(get_public_schema_name()):
            CtnSuscripcion.objects.filter(pk=self.suscripcion.pk).update(fecha_fin=timezone.localdate())

        self._analizar()

        self.assertEqual(len(self._pendientes()), 1)

    def test_no_analiza_un_contenedor_que_no_esta_listo(self):
        _periodo(self.anterior.year, self.anterior.month)
        with schema_context(get_public_schema_name()):
            CtnCliente.objects.filter(pk=self.tenant.pk).update(estado=CtnCliente.ESTADO_ERROR)

        self.assertIn('Analizados: 0', self._analizar())
        self.assertEqual(self._pendientes(), [])
