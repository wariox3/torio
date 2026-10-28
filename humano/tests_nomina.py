"""
Pruebas de generar, desgenerar, aprobar y desaprobar una programación de nómina.

Corren contra los catálogos reales (conceptos, conceptos de nómina, tipos de
documento), cargados con `cargar_datos_tenant`: los cálculos dependen de sus
porcentajes y de qué base alimenta cada concepto.
"""
import io
from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from general.models import (
    GenCiudad,
    GenConfiguracion,
    GenContacto,
    GenDocumento,
    GenDocumentoDetalle,
    GenEstado,
    GenIdentificacion,
    GenPais,
    GenTipoPersona,
)
from humano.formatos import FormatoProgramacion
from humano.models import HumContrato, HumCredito, HumGrupo, HumProgramacion
from humano.servicios import (
    ProgramacionError,
    aprobar_programacion,
    cargar_contratos,
    desaprobar_programacion,
    desgenerar_programacion,
    generar_programacion,
)
from humano.servicios.nomina import porcentaje_fondo_solidaridad
from humano.views.programacion import HumProgramacionViewSet

SALARIO_MINIMO = Decimal('1423500')


class GenerarProgramacionTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        # Ver `general/tests.py`: la caché de auditoría no se revierte con el test.
        from general.signals import limpiar_caches

        self.addCleanup(limpiar_caches)
        call_command('cargar_datos_tenant', schema=self.tenant.schema_name, inicial=True, stdout=io.StringIO())
        GenConfiguracion.objects.filter(pk=1).update(
            hum_factor=Decimal('8'),
            hum_salario_minimo=SALARIO_MINIMO,
            hum_auxilio_transporte=Decimal('200000'),
        )

        pais = GenPais.objects.get_or_create(id=1, defaults={'nombre': 'Colombia'})[0]
        estado = GenEstado.objects.get_or_create(id=1, defaults={'nombre': 'Cundinamarca', 'pais': pais})[0]
        ciudad = GenCiudad.objects.get_or_create(id=1, defaults={'nombre': 'Bogotá', 'estado': estado})[0]
        self.contacto = GenContacto.objects.create(
            numero_identificacion='123', nombre_corto='Empleado', direccion='Calle 1', telefono='1',
            correo='e@e.com', identificacion=GenIdentificacion.objects.first(), ciudad=ciudad,
            tipo_persona=GenTipoPersona.objects.first(), empleado=True,
        )
        self.grupo = HumGrupo.objects.create(nombre='Grupo nómina')

    def _contrato(self, **overrides):
        return HumContrato.objects.create(**{
            'fecha_desde': date(2026, 1, 1), 'fecha_hasta': date(2026, 1, 1),
            'salario': Decimal('2000000'), 'auxilio_transporte': True,
            'contrato_tipo_id': 1, 'salud_id': 1, 'pension_id': 1,
            'contacto': self.contacto, 'grupo': self.grupo, **overrides,
        })

    def _programacion(self, **overrides):
        programacion = HumProgramacion.objects.create(**{
            'fecha_desde': date(2026, 3, 1), 'fecha_hasta': date(2026, 3, 15),
            'fecha_hasta_periodo': date(2026, 3, 15), 'dias': 15, 'dias_reales': 15,
            'grupo': self.grupo, 'pago_tipo_id': 1, **overrides,
        })
        cargar_contratos(programacion)
        programacion.refresh_from_db()
        return programacion

    def _lineas(self, programacion):
        """`{concepto_id: pago}` de las líneas de la programación."""
        return dict(
            GenDocumentoDetalle.objects.filter(documento__programacion_detalle__programacion=programacion)
            .values_list('concepto_id', 'pago')
        )

    # ---- generar ----

    def test_nomina_quincena(self):
        self._contrato()
        programacion = generar_programacion(self._programacion())

        # Salario 1.000.000, transporte 100.000; salud y pensión 4 % de 1.000.000.
        self.assertEqual(self._lineas(programacion), {
            1: Decimal('1000000'), 16: Decimal('100000'), 14: Decimal('40000'), 15: Decimal('40000'),
        })
        self.assertTrue(programacion.estado_generado)
        self.assertEqual(programacion.devengado, Decimal('1100000'))
        self.assertEqual(programacion.deduccion, Decimal('80000'))
        self.assertEqual(programacion.total, Decimal('1020000'))

        documento = GenDocumento.objects.get(programacion_detalle__programacion=programacion)
        self.assertEqual(documento.documento_tipo_id, 14)
        self.assertEqual(documento.total, Decimal('1020000'))
        # Provisiones sobre la base de prestación: salario más transporte.
        self.assertEqual(documento.base_prestacion, Decimal('1100000'))
        self.assertEqual(documento.provision_prima, Decimal('91630'))

    def test_fondo_de_solidaridad_desde_cuatro_minimos(self):
        self._contrato(salario=Decimal('12000000'), auxilio_transporte=False)
        programacion = generar_programacion(self._programacion())

        # Quincena de 6.000.000 = 4,2 mínimos → 1 %.
        self.assertEqual(self._lineas(programacion)[20], Decimal('60000'))

    def test_porcentaje_fondo_solidaridad(self):
        self.assertEqual(porcentaje_fondo_solidaridad(SALARIO_MINIMO, SALARIO_MINIMO * 3), 0)
        self.assertEqual(porcentaje_fondo_solidaridad(SALARIO_MINIMO, SALARIO_MINIMO * 4), 1)
        self.assertEqual(porcentaje_fondo_solidaridad(SALARIO_MINIMO, SALARIO_MINIMO * 16), Decimal('1.2'))
        self.assertEqual(porcentaje_fondo_solidaridad(SALARIO_MINIMO, SALARIO_MINIMO * 25), 2)

    def test_descuenta_la_cuota_del_credito(self):
        contrato = self._contrato()
        HumCredito.objects.create(
            contrato=contrato, concepto_id=self._concepto_credito(), fecha_inicio=date(2026, 1, 1),
            total=Decimal('300000'), cuota=Decimal('100000'), saldo=Decimal('300000'), cantidad_cuotas=3,
        )
        programacion = generar_programacion(self._programacion())

        self.assertEqual(programacion.deduccion, Decimal('180000'))

    def _crear_credito(self, contrato, **datos):
        from humano.serializers import HumCreditoSerializer

        serializador = HumCreditoSerializer(data={
            'contrato': contrato.id, 'concepto': self._concepto_credito(), 'fecha_inicio': '2026-01-01',
            'total': '300000', 'cuota': '100000', 'cantidad_cuotas': 3, **datos,
        })
        serializador.is_valid(raise_exception=True)
        return serializador.save()

    def test_el_credito_creado_por_la_api_queda_con_saldo_y_se_descuenta(self):
        """Con saldo en cero la nómina no lo tomaba: el saldo lo calcula el servidor."""
        credito = self._crear_credito(self._contrato(), saldo='0', abono='50')

        self.assertEqual((credito.saldo, credito.abono), (Decimal('300000'), 0))
        programacion = generar_programacion(self._programacion())
        self.assertEqual(programacion.deduccion, Decimal('180000'))

    def test_al_cambiar_el_total_el_saldo_descuenta_lo_abonado(self):
        from humano.serializers import HumCreditoSerializer

        credito = self._crear_credito(self._contrato())
        HumCredito.objects.filter(pk=credito.pk).update(abono=Decimal('100000'), saldo=Decimal('200000'))
        credito.refresh_from_db()

        serializador = HumCreditoSerializer(credito, data={'total': '500000'}, partial=True)
        serializador.is_valid(raise_exception=True)
        credito = serializador.save()

        self.assertEqual(credito.saldo, Decimal('400000'))

        # Editar otra cosa no toca el saldo.
        serializador = HumCreditoSerializer(credito, data={'comentario': 'x'}, partial=True)
        serializador.is_valid(raise_exception=True)
        self.assertEqual(serializador.save().saldo, Decimal('400000'))

    def test_el_total_no_puede_quedar_por_debajo_de_lo_abonado(self):
        from humano.serializers import HumCreditoSerializer

        credito = self._crear_credito(self._contrato())
        HumCredito.objects.filter(pk=credito.pk).update(abono=Decimal('100000'), saldo=Decimal('200000'))
        credito.refresh_from_db()

        serializador = HumCreditoSerializer(credito, data={'total': '50000'}, partial=True)

        self.assertFalse(serializador.is_valid())
        self.assertIn('abonado', str(serializador.errors['detail']))

    # ---- tope del crédito al aprobar ----

    def _dos_quincenas_con_credito(self, total):
        """Las dos quincenas de marzo generadas antes de aprobar: las dos leen el mismo saldo."""
        credito = HumCredito.objects.create(
            contrato=self._contrato(), concepto_id=self._concepto_credito(), fecha_inicio=date(2026, 1, 1),
            total=Decimal(total), cuota=Decimal('100000'), saldo=Decimal(total), cantidad_cuotas=2,
        )
        primera = generar_programacion(self._programacion())
        segunda = generar_programacion(self._programacion(
            fecha_desde=date(2026, 3, 16), fecha_hasta=date(2026, 3, 31),
        ))
        return credito, primera, segunda

    def test_no_se_aprueba_si_el_credito_pasaria_de_su_total(self):
        credito, primera, segunda = self._dos_quincenas_con_credito('150000')
        aprobar_programacion(primera)

        with self.assertRaises(ProgramacionError) as caso:
            aprobar_programacion(segunda)

        self.assertIn('más de lo que deben', caso.exception.detail)
        self.assertEqual(len(caso.exception.errores), 1)
        self.assertIn('solo le quedan 50,000.00', caso.exception.errores[0]['mensaje'])
        # No queda nada a medias: ni la programación ni sus documentos aprobados, ni el crédito abonado.
        segunda.refresh_from_db()
        self.assertFalse(segunda.estado_aprobado)
        self.assertFalse(
            GenDocumento.objects.filter(programacion_detalle__programacion=segunda, estado_aprobado=True).exists()
        )
        credito.refresh_from_db()
        self.assertEqual((credito.abono, credito.saldo), (Decimal('100000'), Decimal('50000')))

    def test_se_aprueba_si_el_credito_llega_justo_a_su_total(self):
        credito, primera, segunda = self._dos_quincenas_con_credito('200000')
        aprobar_programacion(primera)
        aprobar_programacion(segunda)

        credito.refresh_from_db()
        self.assertEqual((credito.abono, credito.saldo, credito.cuota_actual), (Decimal('200000'), 0, 2))

    def test_el_credito_sin_saldo_queda_pagado_y_al_desaprobar_vuelve_a_pendiente(self):
        credito, primera, segunda = self._dos_quincenas_con_credito('200000')

        aprobar_programacion(primera)
        credito.refresh_from_db()
        self.assertFalse(credito.pagado)

        segunda = aprobar_programacion(segunda)
        credito.refresh_from_db()
        self.assertTrue(credito.pagado)

        desaprobar_programacion(segunda)
        credito.refresh_from_db()
        self.assertEqual((credito.saldo, credito.pagado), (Decimal('100000'), False))

    # ---- validar créditos ----

    def _credito_abonado(self):
        """Un crédito de 300.000 con una cuota de 100.000 descontada en una nómina aprobada."""
        credito = HumCredito.objects.create(
            contrato=self._contrato(), concepto_id=self._concepto_credito(), fecha_inicio=date(2026, 1, 1),
            total=Decimal('300000'), cuota=Decimal('100000'), saldo=Decimal('300000'), cantidad_cuotas=3,
        )
        programacion = aprobar_programacion(generar_programacion(self._programacion()))
        credito.refresh_from_db()
        return credito, programacion

    def test_validar_creditos_corrige_el_que_quedo_desfasado(self):
        from humano.servicios import credito as credito_servicio

        credito, _ = self._credito_abonado()
        HumCredito.objects.filter(pk=credito.pk).update(abono=0, saldo=0, cuota_actual=0)

        self.assertEqual(credito_servicio.validar(), 1)

        credito.refresh_from_db()
        self.assertEqual(
            (credito.abono, credito.saldo, credito.cuota_actual),
            (Decimal('100000'), Decimal('200000'), 1),
        )

    def test_validar_creditos_no_toca_los_que_cuadran(self):
        from humano.servicios import credito as credito_servicio

        self._credito_abonado()

        self.assertEqual(credito_servicio.validar(), 0)

    def test_validar_creditos_no_cuenta_nominas_sin_aprobar_ni_anuladas(self):
        from humano.servicios import credito as credito_servicio

        credito, programacion = self._credito_abonado()
        GenDocumento.objects.filter(programacion_detalle__programacion=programacion).update(estado_anulado=True)
        # Una nómina generada y sin aprobar tampoco abona.
        generar_programacion(self._programacion(fecha_desde=date(2026, 3, 16), fecha_hasta=date(2026, 3, 31)))

        self.assertEqual(credito_servicio.validar(), 1)

        credito.refresh_from_db()
        self.assertEqual((credito.abono, credito.saldo, credito.cuota_actual), (0, Decimal('300000'), 0))

    def test_validar_creditos_por_la_api(self):
        from humano.views.credito import HumCreditoViewSet

        credito, _ = self._credito_abonado()
        HumCredito.objects.filter(pk=credito.pk).update(saldo=0)
        vista = type('Vista', (HumCreditoViewSet,), {
            'authentication_classes': [], 'permission_classes': [permissions.AllowAny], 'throttle_classes': [],
        }).as_view({'post': 'validar'})

        respuesta = vista(APIRequestFactory().post('/', {}, format='json'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data, {'ejecutado': True, 'corregidos': 1})

    def test_prima(self):
        self._contrato()
        programacion = self._programacion(
            pago_tipo_id=2, fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 6, 30),
            fecha_hasta_periodo=date(2026, 6, 30), dias=180,
        )
        programacion = generar_programacion(programacion)

        # 2.200.000 (salario + transporte) × 180 / 360.
        self.assertEqual(self._lineas(programacion)[32], Decimal('1100000'))
        documento = GenDocumento.objects.get(programacion_detalle__programacion=programacion)
        self.assertEqual(documento.documento_tipo_id, 20)

    def test_no_genera_dos_veces(self):
        self._contrato()
        programacion = generar_programacion(self._programacion())

        with self.assertRaises(ProgramacionError):
            generar_programacion(programacion)
        self.assertEqual(GenDocumento.objects.count(), 1)

    def test_sin_detalles_no_genera(self):
        with self.assertRaises(ProgramacionError):
            generar_programacion(self._programacion())

    # ---- desgenerar ----

    def test_desgenerar_borra_documentos_y_totales(self):
        self._contrato()
        programacion = desgenerar_programacion(generar_programacion(self._programacion()))

        self.assertFalse(programacion.estado_generado)
        self.assertEqual(programacion.total, 0)
        self.assertFalse(GenDocumento.objects.exists())
        self.assertFalse(GenDocumentoDetalle.objects.exists())

    # ---- aprobar y desaprobar ----

    def test_aprobar_numera_deja_cartera_y_mueve_contrato(self):
        contrato = self._contrato()
        credito = HumCredito.objects.create(
            contrato=contrato, concepto_id=self._concepto_credito(), fecha_inicio=date(2026, 1, 1),
            total=Decimal('300000'), cuota=Decimal('100000'), saldo=Decimal('300000'), cantidad_cuotas=3,
        )
        programacion = aprobar_programacion(generar_programacion(self._programacion()))

        self.assertTrue(programacion.estado_aprobado)
        documento = GenDocumento.objects.get(programacion_detalle__programacion=programacion)
        self.assertTrue(documento.estado_aprobado)
        self.assertIsNotNone(documento.numero)
        self.assertEqual(documento.pendiente, documento.total)
        contrato.refresh_from_db()
        self.assertEqual(contrato.fecha_ultimo_pago, date(2026, 3, 15))
        credito.refresh_from_db()
        self.assertEqual((credito.saldo, credito.abono, credito.cuota_actual), (Decimal('200000'), Decimal('100000'), 1))

        programacion = desaprobar_programacion(programacion)

        self.assertFalse(programacion.estado_aprobado)
        documento.refresh_from_db()
        self.assertFalse(documento.estado_aprobado)
        self.assertEqual(documento.pendiente, 0)
        contrato.refresh_from_db()
        # No hay otra nómina aprobada: vuelve a no tener último pago.
        self.assertIsNone(contrato.fecha_ultimo_pago)
        credito.refresh_from_db()
        self.assertEqual((credito.saldo, credito.abono, credito.cuota_actual), (Decimal('300000'), 0, 0))

    def test_desaprobar_vuelve_a_la_nomina_aprobada_anterior(self):
        contrato = self._contrato()
        aprobar_programacion(generar_programacion(self._programacion()))
        segunda = self._programacion(
            fecha_desde=date(2026, 3, 16), fecha_hasta=date(2026, 3, 30), fecha_hasta_periodo=date(2026, 3, 31),
        )
        segunda = aprobar_programacion(generar_programacion(segunda))
        contrato.refresh_from_db()
        self.assertEqual(contrato.fecha_ultimo_pago, date(2026, 3, 30))

        desaprobar_programacion(segunda)

        contrato.refresh_from_db()
        self.assertEqual(contrato.fecha_ultimo_pago, date(2026, 3, 15))

    def test_no_aprueba_con_contrato_sin_terminar_vencido(self):
        self._contrato(contrato_tipo_id=2, fecha_hasta=date(2026, 2, 28))
        programacion = generar_programacion(self._programacion())

        with self.assertRaises(ProgramacionError) as error:
            aprobar_programacion(programacion)
        self.assertEqual(len(error.exception.errores), 1)
        self.assertFalse(GenDocumento.objects.filter(estado_aprobado=True).exists())

    def test_no_desaprueba_si_ya_tiene_egreso(self):
        self._contrato()
        programacion = aprobar_programacion(generar_programacion(self._programacion()))
        GenDocumento.objects.update(afectado=Decimal('1000'))

        with self.assertRaises(ProgramacionError):
            desaprobar_programacion(programacion)
        programacion.refresh_from_db()
        self.assertTrue(programacion.estado_aprobado)

    def test_no_desgenera_aprobada(self):
        self._contrato()
        programacion = aprobar_programacion(generar_programacion(self._programacion()))

        with self.assertRaises(ProgramacionError):
            desgenerar_programacion(programacion)

    @staticmethod
    def _concepto_credito():
        """Un concepto de deducción del catálogo, para el crédito."""
        from humano.models import HumConcepto

        return HumConcepto.objects.filter(operacion=-1, adicional=True).exclude(pk=20).values_list('id', flat=True)[0]


    # ---- imprimir ----

    def test_imprimir_programacion_generada(self):
        self._contrato()
        programacion = generar_programacion(self._programacion())

        contenido, nombre = FormatoProgramacion(programacion).pdf()

        self.assertTrue(contenido.startswith(b'%PDF'))
        self.assertEqual(nombre, f'programacion{programacion.id}.pdf')

    def test_imprimir_sin_detalles_tambien_sale(self):
        contenido, _ = FormatoProgramacion(self._programacion()).pdf()
        self.assertTrue(contenido.startswith(b'%PDF'))

    def test_endpoint_imprimir(self):
        class Vista(HumProgramacionViewSet):
            authentication_classes = []
            permission_classes = [permissions.AllowAny]
            throttle_classes = []

        self._contrato()
        programacion = generar_programacion(self._programacion())
        vista = Vista.as_view({'post': 'imprimir'}, **Vista.imprimir.kwargs)
        factory = APIRequestFactory()

        respuesta = vista(factory.post('/', {'programacion_id': programacion.id}, format='json'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertEqual(respuesta['Content-Disposition'], f'inline; filename="programacion{programacion.id}.pdf"')
        self.assertEqual(vista(factory.post('/', {'programacion_id': 999999}, format='json')).status_code, 404)
