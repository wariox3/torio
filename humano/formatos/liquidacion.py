"""
La liquidación impresa de un contrato: la hoja que firma el empleado al retirarse.

Arriba quién es y cómo terminó el contrato; en el medio cada prestación con sus
días, su base y desde cuándo se paga; después los adicionales, y al pie las
firmas del empleado y de la empresa.
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from general.models import GenConfiguracion
from humano.models import HumLiquidacionAdicional
from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import CanvasNumerado, MarcaDocumento, anchos, documento_pdf

_GRIS_LINEA = colors.HexColor('#9e9e9e')

# Prestación amplia; días, base, último pago y total iguales.
_ANCHO_PRESTACIONES = anchos(0.36, 0.14, 0.16, 0.16, 0.18)
# Concepto y detalle amplios; adicional y deducción iguales.
_ANCHO_ADICIONALES = anchos(0.30, 0.38, 0.16, 0.16)


def _pesos(valor):
    """La liquidación va en pesos enteros: sin decimales."""
    return f'{valor or 0:,.0f}'


def _texto(valor):
    return '' if valor is None else str(valor)


class FormatoLiquidacion:
    """
    Formato de la liquidación de contrato.

    Mismo contrato que `FormatoProgramacion`: `construir()` devuelve los
    flowables y `pdf()` arma el archivo.
    """

    numerar_paginas = False

    def __init__(self, liquidacion):
        self.liquidacion = liquidacion
        self.estilos = self._estilos()

    def construir(self):
        adicionales = list(
            HumLiquidacionAdicional.objects.filter(liquidacion=self.liquidacion)
            .select_related('concepto').order_by('id')
        )
        flowables = [
            MarcaDocumento(self.liquidacion.id, self.numerar_paginas),
            *EncabezadoEmpresa(titulo='LIQUIDACIÓN DE CONTRATO').construir(),
            Spacer(1, 0.8 * cm),
            self._datos_empleado(),
            Spacer(1, 0.6 * cm),
            self._tabla_prestaciones(),
        ]
        if adicionales:
            flowables += [Spacer(1, 0.6 * cm), self._tabla_adicionales(adicionales)]
        flowables += [Spacer(1, 2.5 * cm), self._firmas()]
        return flowables

    def pdf(self):
        """Devuelve `(contenido, nombre)`."""
        buffer = io.BytesIO()
        documento_pdf(buffer, 'Liquidación de contrato').build(self.construir(), canvasmaker=CanvasNumerado)
        return buffer.getvalue(), f'liquidacion{self.liquidacion.id}.pdf'

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

    def _datos_empleado(self):
        """Quién es, cómo terminó el contrato y dónde se le paga. En tres columnas."""
        liquidacion = self.liquidacion
        contrato = liquidacion.contrato
        contacto = contrato.contacto
        columnas = (
            [
                f'<b>Identificación:</b> {_texto(contacto.numero_identificacion)}',
                f'<b>Empleado:</b> {_texto(contacto.nombre_corto)}',
                f'<b>Correo:</b> {_texto(contacto.correo)}',
                f'<b>Celular:</b> {_texto(contacto.celular)}',
            ],
            [
                f'<b>Ingreso:</b> {_texto(contrato.fecha_desde)}',
                f'<b>Retiro:</b> {_texto(contrato.fecha_hasta)}',
                f'<b>Motivo:</b> {_texto(contrato.motivo_terminacion.nombre if contrato.motivo_terminacion_id else "")}',
                f'<b>Grupo:</b> {_texto(contrato.grupo.nombre if contrato.grupo_id else "")}',
            ],
            [
                f'<b>Días:</b> {_pesos(liquidacion.dias)}',
                f'<b>Salario:</b> {_pesos(liquidacion.salario)}',
                f'<b>Banco:</b> {_texto(contacto.banco.nombre if contacto.banco_id else "")}',
                f'<b>Cuenta:</b> {_texto(contacto.numero_cuenta)}',
            ],
        )
        filas = [[[Paragraph(texto, self.estilos['dato']) for texto in columna] for columna in columnas]]
        if liquidacion.comentario:
            filas.append([Paragraph(f'<b>Comentario:</b> {liquidacion.comentario}', self.estilos['dato']), '', ''])
        tabla = Table(filas, colWidths=anchos(0.36, 0.34, 0.30))
        estilo = [
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]
        if liquidacion.comentario:
            estilo.append(('SPAN', (0, 1), (-1, 1)))
        tabla.setStyle(TableStyle(estilo))
        return tabla

    def _tabla_prestaciones(self):
        estilos = self.estilos
        liquidacion = self.liquidacion
        filas = [[
            Paragraph('Concepto', estilos['columna']),
            Paragraph('Días', estilos['columna_valor']),
            Paragraph('Base', estilos['columna_valor']),
            Paragraph('Último pago', estilos['columna_valor']),
            Paragraph('Total', estilos['columna_valor']),
        ]]
        # La base es sobre la que se calculó cada una: cesantías y prima llevan el
        # auxilio de transporte si el contrato lo tiene, los intereses salen de las
        # cesantías y las vacaciones solo del salario. Ver `servicios.liquidacion.liquidar`.
        base_prestacion = liquidacion.salario
        if liquidacion.contrato.auxilio_transporte:
            configuracion = GenConfiguracion.objects.filter(pk=1).first()
            base_prestacion += (configuracion and configuracion.hum_auxilio_transporte) or 0
        for nombre, dias, base, ultimo_pago, valor in (
            ('Cesantías', liquidacion.dias_cesantia, base_prestacion,
             liquidacion.fecha_ultimo_pago_cesantia, liquidacion.cesantia),
            ('Intereses de cesantías', liquidacion.dias_cesantia, liquidacion.cesantia,
             liquidacion.fecha_ultimo_pago_cesantia, liquidacion.interes),
            ('Prima', liquidacion.dias_prima, base_prestacion,
             liquidacion.fecha_ultimo_pago_prima, liquidacion.prima),
            ('Vacaciones', liquidacion.dias_vacacion, liquidacion.salario,
             liquidacion.fecha_ultimo_pago_vacacion, liquidacion.vacacion),
        ):
            filas.append([
                Paragraph(nombre, estilos['celda']), _pesos(dias), _pesos(base),
                _texto(ultimo_pago), _pesos(valor),
            ])
        filas += [
            [Paragraph('Adicionales', estilos['celda']), '', '', '', _pesos(liquidacion.adicion)],
            [Paragraph('Deducciones', estilos['celda']), '', '', '', _pesos(liquidacion.deduccion)],
            [Paragraph('<b>Total a pagar</b>', estilos['celda']), '', '', '', _pesos(liquidacion.total)],
        ]

        tabla = Table(filas, colWidths=_ANCHO_PRESTACIONES)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
            ('LINEABOVE', (0, -1), (-1, -1), 0.6, _GRIS_LINEA),
            ('FONTNAME', (4, -1), (4, -1), 'Helvetica-Bold'),
        ]))
        return tabla

    def _tabla_adicionales(self, adicionales):
        estilos = self.estilos
        filas = [[
            Paragraph('Adicional', estilos['columna']),
            Paragraph('Detalle', estilos['columna']),
            Paragraph('Adición', estilos['columna_valor']),
            Paragraph('Deducción', estilos['columna_valor']),
        ]]
        for adicional in adicionales:
            filas.append([
                Paragraph(_texto(adicional.concepto.nombre), estilos['celda']),
                Paragraph(_texto(adicional.detalle), estilos['celda']),
                _pesos(adicional.adicional),
                _pesos(adicional.deduccion),
            ])

        tabla = Table(filas, colWidths=_ANCHO_ADICIONALES, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
        ]))
        return tabla

    def _firmas(self):
        """Empleado y empresa, como las firmas de los formatos de `general`."""
        contacto = self.liquidacion.contrato.contacto
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
