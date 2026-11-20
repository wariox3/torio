"""
La vacación impresa: la hoja que firma el empleado al salir a vacaciones.

Arriba quién es; en el medio el periodo que cubre, las fechas del disfrute y los
días y valores, disfrutados y en dinero; al pie las firmas del empleado y de la
empresa. Se imprime aprobada o no: antes sirve de solicitud, después de constancia.
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import CanvasNumerado, MarcaDocumento, anchos, documento_pdf

_GRIS_LINEA = colors.HexColor('#9e9e9e')

# Concepto amplio; días, valor por día y total iguales.
_ANCHO_VALORES = anchos(0.40, 0.20, 0.20, 0.20)


def _pesos(valor):
    """Las vacaciones van en pesos enteros: sin decimales."""
    return f'{valor or 0:,.0f}'


def _dias(valor):
    """Los días pueden ser fraccionarios (7.5): sin ceros sobrantes."""
    valor = valor or 0
    return f'{valor:,.0f}' if valor == int(valor) else f'{valor.normalize():,}'


def _texto(valor):
    return '' if valor is None else str(valor)


class FormatoVacacion:
    """
    Formato de la novedad de vacaciones.

    Mismo contrato que `FormatoLiquidacion`: `construir()` devuelve los
    flowables y `pdf()` arma el archivo.
    """

    numerar_paginas = False

    def __init__(self, novedad):
        self.novedad = novedad
        self.estilos = self._estilos()

    def construir(self):
        return [
            MarcaDocumento(self.novedad.id, self.numerar_paginas),
            *EncabezadoEmpresa(titulo='VACACIONES').construir(),
            Spacer(1, 0.8 * cm),
            self._datos_empleado(),
            Spacer(1, 0.6 * cm),
            self._fechas(),
            Spacer(1, 0.6 * cm),
            self._tabla_valores(),
            *self._detalle(),
            Spacer(1, 2.5 * cm),
            self._firmas(),
        ]

    def pdf(self):
        """Devuelve `(contenido, nombre)`."""
        buffer = io.BytesIO()
        documento_pdf(buffer, 'Vacaciones').build(self.construir(), canvasmaker=CanvasNumerado)
        return buffer.getvalue(), f'vacacion{self.novedad.id}.pdf'

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
            'firma': ParagraphStyle('firma', parent=base['Normal'], fontSize=9, leading=12, alignment=TA_CENTER),
        }

    def _columnas(self, columnas, ancho):
        """Columnas de párrafos `<b>Etiqueta:</b> valor`, sin bordes."""
        filas = [[[Paragraph(texto, self.estilos['dato']) for texto in columna] for columna in columnas]]
        tabla = Table(filas, colWidths=ancho)
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return tabla

    def _datos_empleado(self):
        """Quién es y su contrato. En tres columnas."""
        novedad = self.novedad
        contrato = novedad.contrato
        contacto = contrato.contacto
        return self._columnas((
            [
                f'<b>Identificación:</b> {_texto(contacto.numero_identificacion)}',
                f'<b>Empleado:</b> {_texto(contacto.nombre_corto)}',
                f'<b>Cargo:</b> {_texto(contrato.cargo.nombre if contrato.cargo_id else "")}',
            ],
            [
                f'<b>Contrato:</b> {_texto(contrato.id)}',
                f'<b>Ingreso:</b> {_texto(contrato.fecha_desde)}',
                f'<b>Grupo:</b> {_texto(contrato.grupo.nombre if contrato.grupo_id else "")}',
            ],
            [
                f'<b>Vacación:</b> {_texto(novedad.id)}',
                f'<b>Salario:</b> {_pesos(contrato.salario)}',
                f'<b>Estado:</b> {"Aprobada" if novedad.estado_aprobado else "Pendiente"}',
            ],
        ), anchos(0.36, 0.34, 0.30))

    def _fechas(self):
        """El periodo que cubre y cuándo las disfruta."""
        novedad = self.novedad
        return self._columnas((
            [
                '<b>Periodo causado</b>',
                f'<b>Desde:</b> {_texto(novedad.fecha_desde_periodo)}',
                f'<b>Hasta:</b> {_texto(novedad.fecha_hasta_periodo)}',
            ],
            [
                '<b>Disfrute</b>',
                f'<b>Desde:</b> {_texto(novedad.fecha_desde)}',
                f'<b>Hasta:</b> {_texto(novedad.fecha_hasta)}',
            ],
        ), anchos(0.50, 0.50))

    def _tabla_valores(self):
        estilos = self.estilos
        novedad = self.novedad
        filas = [
            [
                Paragraph('Concepto', estilos['columna']),
                Paragraph('Días', estilos['columna_valor']),
                Paragraph('Valor día', estilos['columna_valor']),
                Paragraph('Total', estilos['columna_valor']),
            ],
            # Los hábiles son los que cuentan para el periodo; los reales (con
            # domingos y festivos) son los que se pagan.
            [Paragraph('Días hábiles disfrutados', estilos['celda']), _dias(novedad.dias_disfrutados), '', ''],
            [
                Paragraph('Disfrute (días reales)', estilos['celda']),
                _dias(novedad.dias_disfrutados_reales),
                _pesos(novedad.pago_dia_disfrute),
                _pesos(novedad.pago_disfrute),
            ],
            [
                Paragraph('En dinero', estilos['celda']),
                _dias(novedad.dias_dinero),
                '',
                _pesos(novedad.pago_dinero),
            ],
            [Paragraph('<b>Total</b>', estilos['celda']), '', '', _pesos(novedad.total)],
        ]

        tabla = Table(filas, colWidths=_ANCHO_VALORES)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
            ('LINEABOVE', (0, -1), (-1, -1), 0.6, _GRIS_LINEA),
            ('FONTNAME', (3, -1), (3, -1), 'Helvetica-Bold'),
        ]))
        return tabla

    def _detalle(self):
        if not self.novedad.detalle:
            return []
        return [
            Spacer(1, 0.6 * cm),
            Paragraph(f'<b>Detalle:</b> {self.novedad.detalle}', self.estilos['dato']),
        ]

    def _firmas(self):
        """Empleado y empresa, como en la liquidación."""
        contacto = self.novedad.contrato.contacto
        estilo = self.estilos['firma']
        tabla = Table(
            [[
                Paragraph(
                    f'Empleado<br/>{_texto(contacto.nombre_corto)}<br/>C.C. {_texto(contacto.numero_identificacion)}',
                    estilo,
                ),
                # Una columna vacía en el medio: sin ella las dos líneas de firma
                # se tocan y se leen como una sola.
                '',
                Paragraph('Empresa', estilo),
            ]],
            colWidths=anchos(0.4, 0.2, 0.4),
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEABOVE', (0, 0), (0, 0), 0.6, colors.black),
            ('LINEABOVE', (2, 0), (2, 0), 0.6, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        return tabla
