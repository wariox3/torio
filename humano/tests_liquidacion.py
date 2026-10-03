"""
Pruebas de la liquidación de contrato: terminar el contrato, calcular las
prestaciones, generar, aprobar y sus reversas, los adicionales y el PDF.

Corren sobre los catálogos reales (conceptos 30/33/35/37, documento tipo 28 y
motivos de terminación), como las del aporte.
"""
import io
from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from general.models import (
    GenConfiguracion,
    GenContacto,
    GenDocumento,
    GenDocumentoDetalle,
    GenIdentificacion,
    GenTipoPersona,
)
from humano.models import HumContrato, HumGrupo, HumLiquidacion, HumLiquidacionAdicional, HumMotivoTerminacion
from humano.servicios import (
    LiquidacionError,
    aprobar_liquidacion,
    desaprobar_liquidacion,
    desgenerar_liquidacion,
    generar_liquidacion,
    liquidar,
    terminar_contrato,
)

CONCEPTO_BONIFICACION = 30
CONCEPTO_DESCUENTO = 37


class LiquidacionBase(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        from general.signals import limpiar_caches

        self.addCleanup(limpiar_caches)
        call_command('cargar_datos_tenant', schema=self.tenant.schema_name, inicial=True, stdout=io.StringIO())
        GenConfiguracion.objects.filter(pk=1).update(
            hum_factor=Decimal('8'), hum_salario_minimo=Decimal('1423500'),
            hum_auxilio_transporte=Decimal('200000'),
        )
        self.contacto = GenContacto.objects.create(
            numero_identificacion='1036000111', nombre_corto='PEREZ GOMEZ JUAN', nombre1='JUAN',
            apellido1='PEREZ', direccion='Calle 1', telefono='1', correo='e@e.com',
            identificacion=GenIdentificacion.objects.first(), ciudad_id=1,
            tipo_persona=GenTipoPersona.objects.first(), empleado=True,
        )
        self.contrato = HumContrato.objects.create(
            fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 1, 1), salario=Decimal('2000000'),
            auxilio_transporte=True, contrato_tipo_id=1, contacto=self.contacto,
            grupo=HumGrupo.objects.create(nombre='Grupo liquidación'),
        )
        self.motivo = HumMotivoTerminacion.objects.first()

    def _terminar(self, fecha=date(2026, 6, 30)):
        return terminar_contrato(self.contrato, fecha, self.motivo)

    def _adicional(self, liquidacion, adicional=0, deduccion=0, concepto_id=CONCEPTO_BONIFICACION):
        return HumLiquidacionAdicional.objects.create(
            liquidacion=liquidacion, concepto_id=concepto_id,
            adicional=Decimal(adicional), deduccion=Decimal(deduccion),
        )


class LiquidarTests(LiquidacionBase):

    def test_terminar_calcula_las_prestaciones_de_un_semestre(self):
        liquidacion = self._terminar()

        self.contrato.refresh_from_db()
        self.assertTrue(self.contrato.estado_terminado)
        self.assertEqual(self.contrato.fecha_hasta, date(2026, 6, 30))
        self.assertEqual(self.contrato.motivo_terminacion, self.motivo)

        self.assertEqual(liquidacion.dias, 180)
        # Cesantías y prima con auxilio (2.200.000); vacaciones solo con salario.
        self.assertEqual(liquidacion.cesantia, Decimal('1100000'))
        self.assertEqual(liquidacion.interes, Decimal('66000'))
        self.assertEqual(liquidacion.prima, Decimal('1100000'))
        self.assertEqual(liquidacion.vacacion, Decimal('500000'))
        self.assertEqual(liquidacion.total, Decimal('2766000'))
        self.assertEqual(liquidacion.salario, Decimal('2000000'))

    def test_cada_prestacion_cuenta_desde_su_ultimo_pago(self):
        self.contrato.fecha_ultimo_pago_prima = date(2026, 3, 31)
        self.contrato.save()

        liquidacion = self._terminar()

        self.assertEqual(liquidacion.dias_prima, 90)
        self.assertEqual(liquidacion.prima, Decimal('550000'))
        self.assertEqual(liquidacion.fecha_ultimo_pago_prima, date(2026, 3, 31))
        self.assertEqual(liquidacion.dias_cesantia, 180)
        self.assertEqual(liquidacion.fecha_ultimo_pago_cesantia, date(2026, 1, 1))

    def test_sin_auxilio_de_transporte(self):
        self.contrato.auxilio_transporte = False
        self.contrato.save()

        liquidacion = self._terminar()

        self.assertEqual(liquidacion.cesantia, Decimal('1000000'))
        self.assertEqual(liquidacion.prima, Decimal('1000000'))

    def test_no_termina_un_contrato_terminado(self):
        self._terminar()
        with self.assertRaisesMessage(LiquidacionError, 'ya está terminado'):
            self._terminar()
        self.assertEqual(HumLiquidacion.objects.count(), 1)

    def test_no_termina_antes_del_inicio(self):
        with self.assertRaises(LiquidacionError):
            self._terminar(date(2025, 12, 31))
        self.contrato.refresh_from_db()
        self.assertFalse(self.contrato.estado_terminado)
        self.assertFalse(HumLiquidacion.objects.exists())

    def test_reliquidar_suma_los_adicionales(self):
        liquidacion = self._terminar()
        self._adicional(liquidacion, adicional=100000)
        self._adicional(liquidacion, deduccion=30000, concepto_id=CONCEPTO_DESCUENTO)

        liquidacion = liquidar(liquidacion)

        self.assertEqual((liquidacion.adicion, liquidacion.deduccion), (Decimal('100000'), Decimal('30000')))
        self.assertEqual(liquidacion.total, Decimal('2836000'))

    def test_no_reliquida_una_liquidacion_generada(self):
        liquidacion = generar_liquidacion(self._terminar())
        with self.assertRaises(LiquidacionError):
            liquidar(liquidacion)


class CicloLiquidacionTests(LiquidacionBase):

    def test_generar_crea_el_documento_con_una_linea_por_prestacion_y_adicional(self):
        liquidacion = self._terminar()
        self._adicional(liquidacion, adicional=100000)
        self._adicional(liquidacion, deduccion=30000, concepto_id=CONCEPTO_DESCUENTO)
        liquidacion = liquidar(liquidacion)

        liquidacion = generar_liquidacion(liquidacion)

        self.assertTrue(liquidacion.estado_generado)
        documento = GenDocumento.objects.get(liquidacion=liquidacion)
        self.assertEqual(documento.documento_tipo_id, 28)
        self.assertEqual(documento.contacto_id, self.contacto.id)
        self.assertEqual(documento.devengado, Decimal('2866000'))
        self.assertEqual(documento.deduccion, Decimal('30000'))
        self.assertEqual(documento.total, liquidacion.total)
        lineas = list(GenDocumentoDetalle.objects.filter(documento=documento).order_by('id').values_list('concepto_id', 'pago', 'operacion'))
        self.assertEqual(lineas, [
            (35, Decimal('1100000'), 1),
            (37, Decimal('66000'), 1),
            (33, Decimal('1100000'), 1),
            (30, Decimal('500000'), 1),
            (CONCEPTO_BONIFICACION, Decimal('100000'), 1),
            # Descuenta aunque su concepto devengue.
            (CONCEPTO_DESCUENTO, Decimal('30000'), -1),
        ])

    def test_desgenerar_borra_el_documento(self):
        liquidacion = generar_liquidacion(self._terminar())

        liquidacion = desgenerar_liquidacion(liquidacion)

        self.assertFalse(liquidacion.estado_generado)
        self.assertFalse(GenDocumento.objects.filter(liquidacion=liquidacion).exists())
        self.assertEqual(liquidacion.total, Decimal('2766000'))

    def test_aprobar_y_desaprobar(self):
        liquidacion = generar_liquidacion(self._terminar())

        liquidacion = aprobar_liquidacion(liquidacion)

        self.assertTrue(liquidacion.estado_aprobado)
        documento = GenDocumento.objects.get(liquidacion=liquidacion)
        self.assertTrue(documento.estado_aprobado)
        self.assertTrue(documento.numero)
        self.assertEqual(documento.pendiente, documento.total)

        with self.assertRaises(LiquidacionError):
            desgenerar_liquidacion(liquidacion)

        liquidacion = desaprobar_liquidacion(liquidacion)

        self.assertFalse(liquidacion.estado_aprobado)
        documento.refresh_from_db()
        self.assertFalse(documento.estado_aprobado)

    def test_no_aprueba_sin_generar(self):
        with self.assertRaisesMessage(LiquidacionError, 'no está generada'):
            aprobar_liquidacion(self._terminar())

    def test_no_aprueba_un_total_negativo(self):
        liquidacion = self._terminar()
        self._adicional(liquidacion, deduccion=5000000, concepto_id=CONCEPTO_DESCUENTO)
        liquidacion = generar_liquidacion(liquidar(liquidacion))

        with self.assertRaisesMessage(LiquidacionError, 'negativo'):
            aprobar_liquidacion(liquidacion)


class LiquidacionApiTests(LiquidacionBase):

    def setUp(self):
        super().setUp()
        from humano.views.contrato import HumContratoViewSet
        from humano.views.liquidacion import HumLiquidacionViewSet
        from humano.views.liquidacion_adicional import HumLiquidacionAdicionalViewSet

        def abierta(clase):
            return type('Vista', (clase,), {
                'authentication_classes': [], 'permission_classes': [permissions.AllowAny], 'throttle_classes': [],
            })

        self.factory = APIRequestFactory()
        self.terminar = abierta(HumContratoViewSet).as_view({'post': 'terminar'})
        self.imprimir = abierta(HumLiquidacionViewSet).as_view({'post': 'imprimir'})
        self.generar = abierta(HumLiquidacionViewSet).as_view({'post': 'generar'})
        self.editar = abierta(HumLiquidacionViewSet).as_view({'patch': 'partial_update', 'delete': 'destroy'})
        self.adicional = abierta(HumLiquidacionAdicionalViewSet).as_view({'post': 'create'})
        self.adicional_detalle = abierta(HumLiquidacionAdicionalViewSet).as_view({'delete': 'destroy'})

    def _post(self, vista, datos, **kwargs):
        return vista(self.factory.post('/', datos, format='json'), **kwargs)

    def test_terminar_responde_la_liquidacion(self):
        respuesta = self._post(self.terminar, {
            'contrato_id': self.contrato.id, 'fecha_terminacion': '2026-06-30',
            'motivo_terminacion_id': self.motivo.id,
        })

        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(Decimal(respuesta.data['total']), Decimal('2766000'))

    def test_terminar_con_motivo_inexistente(self):
        respuesta = self._post(self.terminar, {
            'contrato_id': self.contrato.id, 'fecha_terminacion': '2026-06-30', 'motivo_terminacion_id': 999,
        })

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)

    def test_los_adicionales_mueven_los_totales(self):
        liquidacion = self._terminar()

        respuesta = self._post(self.adicional, {
            'liquidacion': liquidacion.id, 'concepto': CONCEPTO_BONIFICACION, 'adicional': '100000',
        })
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        liquidacion.refresh_from_db()
        self.assertEqual((liquidacion.adicion, liquidacion.total), (Decimal('100000'), Decimal('2866000')))

        respuesta = self.adicional_detalle(self.factory.delete('/'), pk=respuesta.data['id'])
        self.assertEqual(respuesta.status_code, 204)
        liquidacion.refresh_from_db()
        self.assertEqual((liquidacion.adicion, liquidacion.total), (Decimal('0'), Decimal('2766000')))

    def test_no_entran_adicionales_a_una_liquidacion_generada(self):
        liquidacion = generar_liquidacion(self._terminar())

        respuesta = self._post(self.adicional, {
            'liquidacion': liquidacion.id, 'concepto': CONCEPTO_BONIFICACION, 'adicional': '100000',
        })

        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(HumLiquidacionAdicional.objects.exists())

    def test_adicional_sin_valor(self):
        liquidacion = self._terminar()

        respuesta = self._post(self.adicional, {'liquidacion': liquidacion.id, 'concepto': CONCEPTO_BONIFICACION})

        self.assertEqual(respuesta.status_code, 400)

    def test_no_se_edita_ni_elimina_generada(self):
        liquidacion = generar_liquidacion(self._terminar())

        respuesta = self.editar(self.factory.patch('/', {'comentario': 'x'}, format='json'), pk=liquidacion.id)
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self.editar(self.factory.delete('/'), pk=liquidacion.id)
        self.assertEqual(respuesta.status_code, 400)

    def test_eliminar_se_lleva_los_adicionales(self):
        liquidacion = self._terminar()
        self._adicional(liquidacion, adicional=100000)

        respuesta = self.editar(self.factory.delete('/'), pk=liquidacion.id)

        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(HumLiquidacion.objects.exists())

    def test_generar_liquidacion_inexistente(self):
        self.assertEqual(self._post(self.generar, {'liquidacion_id': 999}).status_code, 404)

    def test_imprimir(self):
        liquidacion = self._terminar()
        self._adicional(liquidacion, adicional=100000)

        respuesta = self._post(self.imprimir, {'liquidacion_id': liquidacion.id})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertTrue(respuesta.content.startswith(b'%PDF'))
