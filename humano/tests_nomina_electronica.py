"""
Pruebas de cómo se arman los conceptos de la nómina electrónica.

`_conceptos` solo lee atributos de las líneas, así que basta con objetos en
memoria: no hace falta base de datos.
"""
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from humano.servicios.nomina_electronica import (
    CONCEPTO_TIPO_NO_SALARIAL,
    CONCEPTO_TIPO_SALARIAL,
    _conceptos,
)


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
