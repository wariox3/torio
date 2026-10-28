"""
Pruebas del desprendible de nómina: qué tipos lo usan, que el PDF salga con
los documentos reales de una programación, `programacion/imprimir-nominas/` y
`programacion/notificar/` con su tarea de Celery.
"""
import base64
import io
from datetime import date
from decimal import Decimal
from unittest import mock

from celery.exceptions import Retry
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from general.formatos import FormatoDocumentoGenerico, FormatoDocumentoNomina
from general.models import GenConfiguracion, GenContacto, GenDocumento, GenIdentificacion, GenTipoPersona
from general.servicios import documento_imprimir
from humano import tasks
from humano.models import HumContrato, HumGrupo, HumMotivoTerminacion, HumProgramacion
from humano.servicios import (
    aprobar_programacion,
    cargar_contratos,
    generar_liquidacion,
    generar_programacion,
    terminar_contrato,
)


class DesprendibleTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        from general.signals import limpiar_caches
        from humano.views.programacion import HumProgramacionViewSet

        self.addCleanup(limpiar_caches)
        call_command('cargar_datos_tenant', schema=self.tenant.schema_name, inicial=True, stdout=io.StringIO())
        GenConfiguracion.objects.filter(pk=1).update(
            hum_factor=Decimal('8'), hum_salario_minimo=Decimal('1423500'),
            hum_auxilio_transporte=Decimal('200000'),
        )
        self.grupo = HumGrupo.objects.create(nombre='Grupo desprendible')
        self.contratos = [
            HumContrato.objects.create(
                fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 1, 1), salario=Decimal('2000000'),
                auxilio_transporte=True, contrato_tipo_id=1, grupo=self.grupo,
                salud_id=1, pension_id=1, tipo_cotizante_id=1, subtipo_cotizante_id=1, riesgo_id=1,
                entidad_salud_id=1, entidad_pension_id=50, entidad_caja_id=70, ciudad_labora_id=1,
                contacto=GenContacto.objects.create(
                    numero_identificacion=numero, nombre_corto=nombre, direccion='Calle 1', telefono='1',
                    correo='e@e.com', identificacion=GenIdentificacion.objects.first(), ciudad_id=1,
                    tipo_persona=GenTipoPersona.objects.first(), empleado=True,
                ),
            )
            for numero, nombre in (('1036000111', 'PEREZ JUAN'), ('1036000222', 'GOMEZ ANA'))
        ]

        class Vista(HumProgramacionViewSet):
            authentication_classes = []
            permission_classes = [permissions.AllowAny]
            throttle_classes = []

        self.imprimir_nominas = Vista.as_view({'post': 'imprimir_nominas'})
        self.notificar = Vista.as_view({'post': 'notificar'})
        self.factory = APIRequestFactory()

    def _programacion(self, generar=True):
        programacion = HumProgramacion.objects.create(
            fecha_desde=date(2026, 3, 1), fecha_hasta=date(2026, 3, 30), fecha_hasta_periodo=date(2026, 3, 31),
            dias=30, dias_reales=30, grupo=self.grupo, pago_tipo_id=1,
        )
        cargar_contratos(programacion)
        return generar_programacion(programacion) if generar else programacion

    def test_los_tipos_de_nomina_usan_el_desprendible(self):
        for documento_tipo_id in (14, 20, 21, 28, 33):
            documento = GenDocumento(documento_tipo_id=documento_tipo_id)
            self.assertIs(documento_imprimir._clase_formato(documento), FormatoDocumentoNomina)
        self.assertIs(documento_imprimir._clase_formato(GenDocumento(documento_tipo_id=29)), FormatoDocumentoGenerico)

    def test_imprime_el_documento_de_nomina(self):
        self._programacion()
        documento = GenDocumento.objects.filter(documento_tipo_id=14).first()

        contenido, nombre = documento_imprimir.pdf_documento(documento)

        self.assertTrue(contenido.startswith(b'%PDF'))
        self.assertTrue(nombre.startswith('nomina'))

    def test_imprime_el_documento_de_la_liquidacion(self):
        liquidacion = terminar_contrato(self.contratos[0], date(2026, 6, 30), HumMotivoTerminacion.objects.first())
        generar_liquidacion(liquidacion)

        contenido, _ = documento_imprimir.pdf_documento(GenDocumento.objects.get(liquidacion=liquidacion))

        self.assertTrue(contenido.startswith(b'%PDF'))

    def test_imprimir_nominas_trae_un_desprendible_por_empleado(self):
        programacion = self._programacion()

        respuesta = self.imprimir_nominas(
            self.factory.post('/', {'programacion_id': programacion.id}, format='json'),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        # Una hoja por empleado: el marcador de página de cada uno queda en el PDF.
        self.assertEqual(respuesta.content.count(b'/Type /Page\n'), 2)

    def test_imprimir_nominas_sin_generar(self):
        programacion = self._programacion(generar=False)

        respuesta = self.imprimir_nominas(
            self.factory.post('/', {'programacion_id': programacion.id}, format='json'),
        )

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('detail', respuesta.data)

    def test_imprimir_nominas_de_programacion_inexistente(self):
        respuesta = self.imprimir_nominas(self.factory.post('/', {'programacion_id': 999}, format='json'))

        self.assertEqual(respuesta.status_code, 404)

    # ---- notificar ----

    def _notificar(self, programacion_id):
        return self.notificar(self.factory.post('/', {'programacion_id': programacion_id}, format='json'))

    def _documento_de(self, contrato):
        return GenDocumento.objects.get(contacto=contrato.contacto, documento_tipo_id=14)

    def test_notificar_programacion_inexistente(self):
        self.assertEqual(self._notificar(999).status_code, 404)

    def test_notificar_sin_aprobar(self):
        programacion = self._programacion()

        with mock.patch.object(tasks.notificar_nomina, 'delay') as delay:
            respuesta = self._notificar(programacion.id)

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(list(respuesta.data), ['detail'])
        delay.assert_not_called()

    def test_notificar_encola_uno_por_empleado_con_correo(self):
        programacion = aprobar_programacion(self._programacion())
        con_correo, sin_correo = self.contratos
        tercero = HumContrato.objects.create(
            fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 1, 1), salario=Decimal('2000000'),
            auxilio_transporte=True, contrato_tipo_id=1, grupo=self.grupo,
            salud_id=1, pension_id=1, tipo_cotizante_id=1, subtipo_cotizante_id=1, riesgo_id=1,
            entidad_salud_id=1, entidad_pension_id=50, entidad_caja_id=70, ciudad_labora_id=1,
            contacto=GenContacto.objects.create(
                numero_identificacion='1036000333', nombre_corto='ZAPATA LUIS', direccion='Calle 1',
                telefono='1', correo='e@e.com', identificacion=GenIdentificacion.objects.first(), ciudad_id=1,
                tipo_persona=GenTipoPersona.objects.first(), empleado=True,
            ),
        )
        # La programación ya está aprobada: el tercero no tiene documento y no cuenta.
        self.assertFalse(GenDocumento.objects.filter(contacto=tercero.contacto).exists())
        GenContacto.objects.filter(pk=sin_correo.contacto_id).update(correo='no-es-correo')

        with mock.patch.object(tasks.notificar_nomina, 'delay') as delay:
            respuesta = self._notificar(programacion.id)

        self.assertEqual(respuesta.status_code, 202)
        self.assertEqual(respuesta.data['encolados'], 1)
        self.assertEqual(respuesta.data['sin_correo'], [{
            'documento_id': self._documento_de(sin_correo).id, 'contacto_nombre_corto': 'GOMEZ ANA',
        }])
        delay.assert_called_once_with(self.tenant.schema_name, self._documento_de(con_correo).id)

    def test_notificar_sin_correo_vacio_tambien_se_reporta(self):
        programacion = aprobar_programacion(self._programacion())
        GenContacto.objects.filter(pk__in=[c.contacto_id for c in self.contratos]).update(correo='')

        with mock.patch.object(tasks.notificar_nomina, 'delay') as delay:
            respuesta = self._notificar(programacion.id)

        self.assertEqual(respuesta.status_code, 202)
        self.assertEqual(respuesta.data['encolados'], 0)
        self.assertEqual(len(respuesta.data['sin_correo']), 2)
        delay.assert_not_called()

    def test_notificar_con_el_broker_caido(self):
        programacion = aprobar_programacion(self._programacion())

        with mock.patch.object(tasks.notificar_nomina, 'delay', side_effect=ConnectionError('amqp')), \
                self.assertLogs('humano.views.programacion', level='ERROR'):
            respuesta = self._notificar(programacion.id)

        self.assertEqual(respuesta.status_code, 503)
        self.assertIn('detail', respuesta.data)

    def test_notificar_se_puede_repetir(self):
        programacion = aprobar_programacion(self._programacion())

        with mock.patch.object(tasks.notificar_nomina, 'delay') as delay:
            self._notificar(programacion.id)
            self._notificar(programacion.id)

        self.assertEqual(delay.call_count, 4)

    # ---- tarea notificar_nomina ----

    def _correr_tarea(self, documento_id, respuesta=None):
        respuesta = respuesta or {'error': False, 'status': 200, 'datos': {}}
        with mock.patch('utilidades.zinc.Zinc') as zinc:
            zinc.return_value.correo.return_value = respuesta
            resultado = tasks.notificar_nomina.apply(args=[self.tenant.schema_name, documento_id])
        return resultado, zinc.return_value.correo

    def test_la_tarea_va_por_su_propia_cola(self):
        from torioapp.celery import app

        ruta = app.amqp.router.route({}, tasks.notificar_nomina.name)
        self.assertEqual(ruta['queue'].name, 'notificar_nomina')

    def test_la_tarea_adjunta_el_desprendible_en_pdf(self):
        aprobar_programacion(self._programacion())
        documento = self._documento_de(self.contratos[0])

        resultado, correo = self._correr_tarea(documento.id)

        self.assertEqual(resultado.state, 'SUCCESS')
        correo.assert_called_once()
        destinatario, asunto, html = correo.call_args.args
        self.assertEqual((destinatario, asunto), ('e@e.com', tasks.ASUNTO_NOMINA))
        self.assertIn('PEREZ JUAN', html)
        [adjunto] = correo.call_args.kwargs['archivos']
        self.assertTrue(base64.b64decode(adjunto['B64']).startswith(b'%PDF'))
        self.assertEqual(adjunto['NombreArchivo'], documento_imprimir.pdf_documento(documento)[1])

    def test_la_tarea_reintenta_si_zinc_no_responde(self):
        aprobar_programacion(self._programacion())
        documento = self._documento_de(self.contratos[0])

        with mock.patch.object(tasks.notificar_nomina, 'retry', side_effect=Retry()) as reintentar:
            resultado, _ = self._correr_tarea(documento.id, {'error': True, 'status': 502, 'datos': 'caído'})

        self.assertEqual(resultado.state, 'RETRY')
        self.assertEqual(reintentar.call_args.kwargs['countdown'], tasks.ESPERA_BASE_REINTENTO)

    def test_la_tarea_no_reintenta_si_zinc_rechaza(self):
        aprobar_programacion(self._programacion())
        documento = self._documento_de(self.contratos[0])

        with mock.patch.object(tasks.notificar_nomina, 'retry') as reintentar, \
                self.assertLogs('humano.tasks', level='WARNING'):
            resultado, _ = self._correr_tarea(documento.id, {'error': True, 'status': 400, 'datos': 'malo'})

        self.assertEqual(resultado.state, 'SUCCESS')
        reintentar.assert_not_called()

    def test_la_tarea_no_envia_si_el_documento_no_existe(self):
        resultado, correo = self._correr_tarea(999999)

        self.assertEqual(resultado.state, 'SUCCESS')
        correo.assert_not_called()

    def test_la_tarea_no_envia_si_el_correo_dejo_de_ser_valido(self):
        aprobar_programacion(self._programacion())
        documento = self._documento_de(self.contratos[0])
        GenContacto.objects.filter(pk=documento.contacto_id).update(correo='ya no')

        resultado, correo = self._correr_tarea(documento.id)

        self.assertEqual(resultado.state, 'SUCCESS')
        correo.assert_not_called()
