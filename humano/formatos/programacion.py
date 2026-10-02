"""
Resumen impreso de una programación de nómina: qué se le paga a cada empleado.

Es la hoja que se revisa antes de aprobar y con la que se arma el pago al banco,
así que va un empleado por fila con su cuenta y su banco, y los totales de la
programación arriba y al pie. El desprendible de cada empleado no es esto: es
el documento de nómina, que se imprime desde `general` como cualquier documento.
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from humano.models import HumProgramacionDetalle
from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import ANCHO_CONTENIDO, CanvasNumerado, MarcaDocumento, anchos, documento_pdf

_GRIS_LINEA = colors.HexColor('#9e9e9e')

# Empleado amplio; cuenta y banco medianos; los tres importes iguales.
_ANCHO_TABLA = anchos(0.40, 0.12, 0.12, 0.12, 0.12, 0.12)


def _pesos(valor):
    """La nómina se liquida en pesos enteros: sin decimales."""
    return f'{valor or 0:,.0f}'


def _texto(valor):
    return '' if valor is None else str(valor)


class FormatoProgramacion:
    """
    Formato de la programación de nómina.

    Mismo contrato que los formatos de `general`: `construir()` devuelve los
    flowables y `pdf()` arma el archivo. No hereda de `FormatoBase` porque aquel
    recibe un documento, y esto es una programación con sus detalles.
    """

    # Una programación con muchos empleados ocupa varias hojas.
    numerar_paginas = True

    def __init__(self, programacion):
        self.programacion = programacion
        self.estilos = self._estilos()

    def construir(self):
        detalles = (
            HumProgramacionDetalle.objects.filter(programacion=self.programacion)
            .select_related('contrato__contacto__banco')
            .order_by('contrato__contacto__nombre_corto', 'id')
        )
        return [
            MarcaDocumento(self.programacion.id, self.numerar_paginas),
            *EncabezadoEmpresa(titulo='PROGRAMACIÓN DE NÓMINA').construir(),
            Spacer(1, 0.8 * cm),
            self._datos_programacion(),
            Spacer(1, 0.6 * cm),
            self._tabla_detalles(detalles),
        ]

    def pdf(self):
        """Devuelve `(contenido, nombre)`."""
        buffer = io.BytesIO()
        documento_pdf(buffer, 'Programación de nómina').build(self.construir(), canvasmaker=CanvasNumerado)
        return buffer.getvalue(), f'programacion{self.programacion.id}.pdf'

    @staticmethod
    def _estilos():
        base = getSampleStyleSheet()
        return {
            'dato': ParagraphStyle('dato', parent=base['Normal'], fontSize=9, leading=13),
            'columna': ParagraphStyle(
                'columna', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=8.5, leading=11,
            ),
            'columna_valor': ParagraphStyle(
                'columna_valor', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=8.5, leading=11, alignment=TA_RIGHT,
            ),
            'celda': ParagraphStyle('celda', parent=base['Normal'], fontSize=8.5, leading=11),
        }

    def _datos_programacion(self):
        """Qué programación es y cuánto suma. En tres columnas para no gastar media hoja."""
        programacion = self.programacion
        columnas = (
            [
                f'<b>Código:</b> {programacion.id}',
                f'<b>Desde:</b> {programacion.fecha_desde}',
                f'<b>Hasta:</b> {programacion.fecha_hasta}',
            ],
            [
                f'<b>Nombre:</b> {_texto(programacion.nombre)}',
                f'<b>Grupo:</b> {_texto(programacion.grupo.nombre)}',
                f'<b>Tipo:</b> {_texto(programacion.pago_tipo.nombre)}',
            ],
            [
                f'<b>Devengado:</b> {_pesos(programacion.devengado)}',
                f'<b>Deducción:</b> {_pesos(programacion.deduccion)}',
                f'<b>Total:</b> {_pesos(programacion.total)}',
            ],
        )
        tabla = Table(
            [[[Paragraph(texto, self.estilos['dato']) for texto in columna] for columna in columnas]],
            colWidths=anchos(0.3, 0.42, 0.28),
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return tabla

    def _tabla_detalles(self, detalles):
        estilos = self.estilos
        filas = [[
            Paragraph('Identificación - Empleado', estilos['columna']),
            Paragraph('Cuenta', estilos['columna']),
            Paragraph('Banco', estilos['columna']),
            Paragraph('Devengado', estilos['columna_valor']),
            Paragraph('Deducción', estilos['columna_valor']),
            Paragraph('Total', estilos['columna_valor']),
        ]]
        for detalle in detalles:
            contacto = detalle.contrato.contacto
            filas.append([
                Paragraph(f'{_texto(contacto.numero_identificacion)} - {_texto(contacto.nombre_corto)}', estilos['celda']),
                Paragraph(_texto(contacto.numero_cuenta), estilos['celda']),
                Paragraph(_texto(contacto.banco.nombre if contacto.banco_id else ''), estilos['celda']),
                _pesos(detalle.devengado),
                _pesos(detalle.deduccion),
                _pesos(detalle.total),
            ])
        programacion = self.programacion
        filas.append([
            Paragraph('<b>Total</b>', estilos['celda']), '', '',
            _pesos(programacion.devengado), _pesos(programacion.deduccion), _pesos(programacion.total),
        ])

        tabla = Table(filas, colWidths=_ANCHO_TABLA, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            # Una línea bajo los encabezados y otra sobre el total: se lee sin grilla.
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
            ('LINEABOVE', (0, -1), (-1, -1), 0.6, _GRIS_LINEA),
            ('FONTNAME', (3, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        return tabla
