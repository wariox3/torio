"""
Pruebas de cómo se arman los conceptos de la nómina electrónica.

`_conceptos` solo lee atributos de las líneas, así que basta con objetos en
memoria: no hace falta base de datos. Generar varias veces en el mismo mes
(nómina por quincena) sí va contra la base.
"""
import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase
from django_tenants.test.cases import TenantTestCase
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from general.models import (
    GenCiudad,
    GenContacto,
    GenDocumento,
    GenEstado,
    GenIdentificacion,
    GenPais,
    GenTipoPersona,
)
from general.servicios import documento as documento_servicio
from general.views.documento import GenDocumentoViewSet
from humano.models import HumContrato, HumGrupo
from humano.servicios import nomina_electronica
from humano.servicios.nomina_electronica import (
    CONCEPTO_TIPO_NO_SALARIAL,
    CONCEPTO_TIPO_SALARIAL,
    _conceptos,
)


DOCUMENTO_TIPO_NOMINA = 14


def _linea(concepto_id, nombre, tipo, pago, numero=1):
    return SimpleNamespace(
        concepto=SimpleNamespace(id=concepto_id, nombre=nombre, concepto_tipo_id=tipo),
        operacion=1, pago=Decimal(pago), documento=SimpleNamespace(numero=numero),
    )


class OtroConceptoTests(SimpleTestCase):
    """Rededoc rechaza dos `otro_concepto` con la misma descripción."""

    def _otros(self, lineas):
        errores = []
        conceptos = _conceptos(lineas, documento=None, errores=errores)
        self.assertEqual(errores, [])
        return [c for c in conceptos if c['concepto'] == 'otro_concepto']

    def test_el_mismo_no_salarial_de_dos_quincenas_va_sumado(self):
        otros = self._otros([
            _linea(13, 'Bonificacion no prestacional', CONCEPTO_TIPO_NO_SALARIAL, 300000, numero=171),
            _linea(13, 'Bonificacion no prestacional', CONCEPTO_TIPO_NO_SALARIAL, 300000, numero=175),
        ])
        self.assertEqual(otros, [{
            'grupo': 'devengado', 'concepto': 'otro_concepto',
            'descripcion': 'Bonificacion no prestacional',
            'valor': '0.00', 'valor_no_salarial': '600000.00',
        }])

    def test_el_mismo_salarial_de_dos_quincenas_va_sumado(self):
        otros = self._otros([
            _linea(40, 'Bono', CONCEPTO_TIPO_SALARIAL, 100000),
            _linea(40, 'Bono', CONCEPTO_TIPO_SALARIAL, 50000),
        ])
        self.assertEqual(otros, [{
            'grupo': 'devengado', 'concepto': 'otro_concepto',
            'descripcion': 'Bono', 'valor': '150000.00',
        }])

    def test_se_agrupa_por_descripcion_como_rededoc(self):
        # Dos conceptos distintos con el mismo nombre (sin importar mayúsculas ni
        # espacios) son el mismo para rededoc: van en una fila con las dos partes.
        otros = self._otros([
            _linea(40, 'Bono', CONCEPTO_TIPO_SALARIAL, 100000),
            _linea(41, ' bono ', CONCEPTO_TIPO_NO_SALARIAL, 20000),
        ])
        self.assertEqual(otros, [{
            'grupo': 'devengado', 'concepto': 'otro_concepto', 'descripcion': 'Bono',
            'valor': '100000.00', 'valor_no_salarial': '20000.00',
        }])

    def test_conceptos_distintos_van_en_filas_distintas(self):
        otros = self._otros([
            _linea(13, 'Bonificacion no prestacional', CONCEPTO_TIPO_NO_SALARIAL, 300000),
            _linea(40, 'Bono', CONCEPTO_TIPO_SALARIAL, 100000),
        ])
        self.assertEqual([o['descripcion'] for o in otros], ['Bonificacion no prestacional', 'Bono'])


class GenerarPorQuincenaTests(TenantTestCase):
    """
    Quien paga por quincena puede reportar la primera antes de tener la segunda.
    Volver a generar crea otra electrónica con las nóminas nuevas, con las
    mismas fechas del mes, y deja la primera como estaba.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.nombre = 'Test'
        tenant.celular = '0'
        tenant.correo = 'test@test.com'

    def setUp(self):
        from general.signals import limpiar_caches

        self.addCleanup(limpiar_caches)
        call_command('cargar_datos_tenant', schema=self.tenant.schema_name, inicial=True, stdout=io.StringIO())
        pais = GenPais.objects.get_or_create(id=1, defaults={'nombre': 'Colombia'})[0]
        estado = GenEstado.objects.get_or_create(id=1, defaults={'nombre': 'Cundinamarca', 'pais': pais})[0]
        ciudad = GenCiudad.objects.get_or_create(id=1, defaults={'nombre': 'Bogotá', 'estado': estado})[0]
        self.contacto = GenContacto.objects.create(
            numero_identificacion='123', nombre_corto='Ana Pérez', nombre1='Ana', apellido1='Pérez',
            direccion='Calle 1', telefono='1', correo='e@e.com',
            identificacion=GenIdentificacion.objects.first(), ciudad=ciudad,
            tipo_persona=GenTipoPersona.objects.first(), empleado=True,
        )
        self.contrato = HumContrato.objects.create(
            fecha_desde=date(2026, 1, 1), fecha_hasta=date(2026, 12, 31), salario=Decimal('2000000'),
            contrato_tipo_id=1, contacto=self.contacto, grupo=HumGrupo.objects.create(nombre='Quincenal'),
        )

    def _nomina(self, fecha, numero):
        return GenDocumento.objects.create(
            documento_tipo_id=DOCUMENTO_TIPO_NOMINA, numero=numero, fecha=fecha,
            contacto=self.contacto, contrato=self.contrato, estado_aprobado=True,
            devengado=Decimal('1000000'), deduccion=Decimal('80000'), total=Decimal('920000'),
        )

    def test_la_segunda_quincena_va_en_otra_electronica_con_las_fechas_del_mes(self):
        primera = self._nomina(date(2026, 11, 15), 1)
        [electronica_1] = nomina_electronica.generar(2026, 11)
        # La primera ya se reportó: generar otra vez no la puede tocar.
        GenDocumento.objects.filter(pk=electronica_1.pk).update(estado_electronico_enviado=True)

        segunda = self._nomina(date(2026, 11, 30), 2)
        [electronica_2] = nomina_electronica.generar(2026, 11)

        self.assertNotEqual(electronica_1.pk, electronica_2.pk)
        primera.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primera.documento_referencia_id, electronica_1.pk)
        self.assertEqual(segunda.documento_referencia_id, electronica_2.pk)
        for electronica in (electronica_1, electronica_2):
            self.assertEqual(
                (electronica.fecha_desde, electronica.fecha_hasta), (date(2026, 11, 1), date(2026, 11, 30)),
            )
            self.assertEqual(electronica.devengado, Decimal('1000000'))
            self.assertTrue(electronica.estado_aprobado)

    def test_sin_nominas_nuevas_no_genera_otra(self):
        self._nomina(date(2026, 11, 15), 1)
        nomina_electronica.generar(2026, 11)

        with self.assertRaises(nomina_electronica.NominaElectronicaError):
            nomina_electronica.generar(2026, 11)

    # ---- desaprobar y eliminar ----

    def test_una_electronica_sin_enviar_se_desaprueba_y_conserva_sus_nominas(self):
        nomina = self._nomina(date(2026, 11, 15), 1)
        [electronica] = nomina_electronica.generar(2026, 11)

        documento_servicio.desaprobar(electronica.id)

        electronica.refresh_from_db()
        nomina.refresh_from_db()
        self.assertFalse(electronica.estado_aprobado)
        self.assertIsNotNone(electronica.numero)
        self.assertEqual(nomina.documento_referencia_id, electronica.pk)
        # Se puede volver a aprobar con el mismo número.
        self.assertTrue(documento_servicio.aprobar(electronica.id).estado_aprobado)

    def test_una_electronica_enviada_no_se_desaprueba(self):
        self._nomina(date(2026, 11, 15), 1)
        [electronica] = nomina_electronica.generar(2026, 11)
        GenDocumento.objects.filter(pk=electronica.pk).update(estado_electronico_enviado=True)

        with self.assertRaises(ValidationError) as caso:
            documento_servicio.desaprobar(electronica.id)

        self.assertIn('enviado', str(caso.exception))

    def test_eliminar_una_electronica_desaprobada_suelta_sus_nominas(self):
        nomina = self._nomina(date(2026, 11, 15), 1)
        [electronica] = nomina_electronica.generar(2026, 11)
        documento_servicio.desaprobar(electronica.id)

        request = APIRequestFactory().delete(f'/general/documento/{electronica.id}/')
        vista = GenDocumentoViewSet.as_view({'delete': 'destroy'})
        with patch.object(GenDocumentoViewSet, 'permission_classes', [permissions.AllowAny]), \
                patch.object(GenDocumentoViewSet, 'authentication_classes', []):
            respuesta = vista(request, pk=electronica.id)

        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(GenDocumento.objects.filter(pk=electronica.pk).exists())
        nomina.refresh_from_db()
        self.assertIsNone(nomina.documento_referencia_id)
        # Suelta, entra en la siguiente generación.
        [otra] = nomina_electronica.generar(2026, 11)
        nomina.refresh_from_db()
        self.assertEqual(nomina.documento_referencia_id, otra.pk)

    # ---- anular ----

    def test_anular_una_electronica_la_deja_como_registro_y_suelta_sus_nominas(self):
        nomina = self._nomina(date(2026, 11, 15), 1)
        [electronica] = nomina_electronica.generar(2026, 11)

        documento_servicio.anular(electronica.id)

        electronica.refresh_from_db()
        nomina.refresh_from_db()
        self.assertTrue(electronica.estado_anulado)
        self.assertIsNotNone(electronica.numero)
        self.assertEqual(electronica.total, 0)
        self.assertIsNone(nomina.documento_referencia_id)
        # Suelta, entra en la siguiente con otro consecutivo.
        [otra] = nomina_electronica.generar(2026, 11)
        nomina.refresh_from_db()
        self.assertEqual(nomina.documento_referencia_id, otra.pk)
        self.assertNotEqual(otra.numero, electronica.numero)

    def test_una_electronica_enviada_no_se_anula_ni_suelta_sus_nominas(self):
        nomina = self._nomina(date(2026, 11, 15), 1)
        [electronica] = nomina_electronica.generar(2026, 11)
        GenDocumento.objects.filter(pk=electronica.pk).update(estado_electronico_enviado=True)

        with self.assertRaises(ValidationError):
            documento_servicio.anular(electronica.id)

        nomina.refresh_from_db()
        self.assertEqual(nomina.documento_referencia_id, electronica.pk)
