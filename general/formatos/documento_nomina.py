"""
Formato de los documentos de nómina: el desprendible que recibe el empleado.

Sirve para todos los tipos de la clase 701 —nómina, prima, cesantía, intereses y
liquidación—, porque los cinco son lo mismo: un pago a un empleado armado con
conceptos que devengan o deducen. Lo que cambia entre ellos es el título, y el
título es el nombre del tipo, como en el genérico.

No reusa el genérico porque una nómina no tiene cantidades ni precios: cada
línea es un concepto con sus horas, sus días y su porcentaje, y lo que se suma es
devengado contra deducción. La firma del empleado al pie es lo que lo vuelve
constancia de que recibió el pago.
"""
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from general.formatos.base import FormatoBase
from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import ANCHO_CONTENIDO, anchos
from utilidades.numero_letras import valor_en_letras

CERO = Decimal('0')

_GRIS_LINEA = colors.HexColor('#9e9e9e')

# Código y porcentaje angostos; concepto y detalle se llevan el ancho; horas y
# días medianos; devengado y deducción iguales, a la medida de un sueldo.
_ANCHO_TABLA = anchos(0.06, 0.27, 0.21, 0.08, 0.06, 0.06, 0.13, 0.13)


class FormatoDocumentoNomina(FormatoBase):
    """Desprendible de nómina: datos del empleado, conceptos, totales y firma."""

    def construir(self):
        documento = self.documento
        estilos = self._estilos()

        return [
            *EncabezadoEmpresa(titulo=documento.documento_tipo.nombre.upper()).construir(),
            Spacer(1, 0.8 * cm),
            self._datos(documento, estilos),
            Spacer(1, 0.6 * cm),
            self._tabla_conceptos(documento, estilos),
            Spacer(1, 0.5 * cm),
            self._totales(documento, estilos),
            Spacer(1, 0.3 * cm),
            Paragraph(f'<b>NETO EN LETRAS:</b> {valor_en_letras(documento.total)}', estilos['letras']),
            Spacer(1, 2.2 * cm),
            self._firma(documento, estilos),
        ]

    @staticmethod
    def _estilos():
        base = getSampleStyleSheet()
        return {
            'dato': ParagraphStyle('dato', parent=base['Normal'], fontSize=9, leading=13),
            'columna': ParagraphStyle(
                'columna', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=8, leading=10,
            ),
            'columna_valor': ParagraphStyle(
                'columna_valor', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=8, leading=10, alignment=TA_RIGHT,
            ),
            'celda': ParagraphStyle('celda', parent=base['Normal'], fontSize=8, leading=10),
            'total': ParagraphStyle(
                'total', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=9, alignment=TA_RIGHT, leading=13,
            ),
            'letras': ParagraphStyle('letras', parent=base['Normal'], fontSize=8.5, leading=12),
            'firma': ParagraphStyle('firma', parent=base['Normal'], fontSize=9, alignment=TA_CENTER, leading=12),
        }

    @staticmethod
    def _texto(valor):
        return '' if valor is None else str(valor)

    @staticmethod
    def _pesos(valor):
        """La nómina se liquida en pesos enteros: sin decimales."""
        return f'{valor or CERO:,.0f}'

    def _datos(self, documento, estilos):
        """Quién, de qué periodo y a dónde se le paga. En tres columnas para no gastar media hoja."""
        contacto = documento.contacto
        contrato = documento.contrato
        texto = self._texto
        columnas = (
            [
                f'<b>Número:</b> {documento.numero if documento.numero is not None else "—"}',
                f'<b>Empleado:</b> {texto(contacto and contacto.nombre_corto)}',
                f'<b>Identificación:</b> {texto(contacto and contacto.numero_identificacion)}',
                f'<b>Cargo:</b> {texto(contrato and contrato.cargo_id and contrato.cargo.nombre)}',
            ],
            [
                f'<b>Desde:</b> {texto(documento.fecha_desde)}',
                f'<b>Hasta:</b> {texto(documento.fecha_hasta)}',
                f'<b>Días:</b> {texto(documento.dias)}',
                f'<b>Grupo:</b> {texto(contrato and contrato.grupo_id and contrato.grupo.nombre)}',
            ],
            [
                f'<b>Salario:</b> {self._pesos(documento.salario)}',
                f'<b>Banco:</b> {texto(contacto and contacto.banco_id and contacto.banco.nombre)}',
                f'<b>Cuenta:</b> {texto(contacto and contacto.numero_cuenta)}',
            ],
        )
        tabla = Table(
            [[[Paragraph(linea, estilos['dato']) for linea in columna] for columna in columnas]],
            colWidths=anchos(0.42, 0.28, 0.30),
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return tabla

    def _tabla_conceptos(self, documento, estilos):
        """Una fila por línea, en el orden de los conceptos: primero lo que devenga."""
        encabezados = (
            ('Cód', 'columna'), ('Concepto', 'columna'), ('Detalle', 'columna'),
            ('Horas', 'columna_valor'), ('Días', 'columna_valor'), ('%', 'columna_valor'),
            ('Devengado', 'columna_valor'), ('Deducción', 'columna_valor'),
        )
        filas = [[Paragraph(texto, estilos[estilo]) for texto, estilo in encabezados]]

        detalles = (
            documento.documentos_detalles_documento_rel
            .select_related('concepto').order_by('concepto__orden', 'id')
        )
        for detalle in detalles:
            filas.append([
                self._texto(detalle.concepto_id),
                Paragraph(self._texto(detalle.concepto_id and detalle.concepto.nombre), estilos['celda']),
                Paragraph(self._texto(detalle.detalle), estilos['celda']),
                f'{detalle.cantidad:,.2f}' if detalle.cantidad else '',
                self._texto(detalle.dias or ''),
                f'{detalle.porcentaje:,.0f}' if detalle.porcentaje else '',
                self._pesos(detalle.devengado) if detalle.devengado else '',
                self._pesos(detalle.deduccion) if detalle.deduccion else '',
            ])

        tabla = Table(filas, colWidths=_ANCHO_TABLA, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
        ]))
        return tabla

    def _totales(self, documento, estilos):
        """Bajo las columnas de devengado y deducción, con el neto separado del resto."""
        lineas = (
            ('Total devengado', documento.devengado),
            ('Total deducciones', documento.deduccion),
            ('Neto a pagar', documento.total),
        )
        filas = [
            ['', Paragraph(f'{etiqueta}:', estilos['total']), Paragraph(self._pesos(valor), estilos['total'])]
            for etiqueta, valor in lineas
        ]
        ancho_etiqueta, ancho_valor = _ANCHO_TABLA[6] * 2, _ANCHO_TABLA[7]
        relleno = ANCHO_CONTENIDO - ancho_etiqueta - ancho_valor

        tabla = Table(filas, colWidths=[relleno, ancho_etiqueta, ancho_valor])
        tabla.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (2, 0), (2, -1), 0),
            ('LINEABOVE', (1, -1), (-1, -1), 0.6, _GRIS_LINEA),
        ]))
        return tabla

    def _firma(self, documento, estilos):
        """La del empleado: con ella el desprendible es constancia de que recibió el pago."""
        contacto = documento.contacto
        ancho = ANCHO_CONTENIDO / 2
        tabla = Table(
            [[Paragraph(
                f'Recibí conforme<br/>{self._texto(contacto and contacto.nombre_corto)}<br/>'
                f'C.C. {self._texto(contacto and contacto.numero_identificacion)}',
                estilos['firma'],
            ), '']],
            colWidths=[ancho, ancho],
        )
        tabla.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (0, 0), 0.6, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 1.5 * cm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1.5 * cm),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        return tabla
