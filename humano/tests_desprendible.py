"""
Pruebas del desprendible de nómina: qué tipos lo usan, que el PDF salga con
los documentos reales de una programación y `programacion/imprimir-nominas/`.
"""
import io
from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.test import APIRequestFactory

from general.formatos import FormatoDocumentoGenerico, FormatoDocumentoNomina
from general.models import GenConfiguracion, GenContacto, GenDocumento, GenIdentificacion, GenTipoPersona
from general.servicios import documento_imprimir
from humano.models import HumContrato, HumGrupo, HumMotivoTerminacion, HumProgramacion
from humano.servicios import cargar_contratos, generar_liquidacion, generar_programacion, terminar_contrato


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
