"""
Resumen impreso de un aporte a seguridad social (PILA): qué se cotiza por cada
línea del aporte.

Va una fila por `HumAporteDetalle`, no por empleado: un contrato con una
incapacidad o unas vacaciones en el mes tiene una línea por cada tramo, igual que
en el plano. Para que eso se lea, cada fila lleva bajo el empleado las marcas de
novedad del plano (ING, RET, IGE, VAC...). Las cotizaciones son las que se le
pagan a cada subsistema, y el total al pie suma las filas impresas.
"""
import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from humano.models import HumAporteDetalle
from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import CanvasNumerado, MarcaDocumento, anchos, documento_pdf

_GRIS_LINEA = colors.HexColor('#9e9e9e')
_GRIS_NOVEDAD = colors.HexColor('#616161')

# Empleado amplio; días angosto; los ocho importes iguales.
_ANCHO_TABLA = anchos(0.235, 0.045, *(0.09,) * 8)

def _pension(detalle):
    # Con el fondo de solidaridad, como `cotizacion_pension_total` del aporte: así
    # la fila suma su total. `total_cotizacion_pension` del detalle no se llena.
    return (
        detalle.cotizacion_pension + detalle.cotizacion_solidaridad_solidaridad
        + detalle.cotizacion_solidaridad_subsistencia
    )


# Las columnas de importe, en orden: (encabezado, cómo se saca del detalle).
_COLUMNAS_VALOR = (
    ('IBC', lambda detalle: detalle.base_cotizacion_salud),
    ('Pensión', _pension),
    ('Salud', lambda detalle: detalle.cotizacion_salud),
    ('Riesgos', lambda detalle: detalle.cotizacion_riesgos),
    ('Caja', lambda detalle: detalle.cotizacion_caja),
    ('SENA', lambda detalle: detalle.cotizacion_sena),
    ('ICBF', lambda detalle: detalle.cotizacion_icbf),
    ('Total', lambda detalle: detalle.cotizacion_total),
)

# Marcas de novedad del detalle, con la sigla del plano PILA.
_NOVEDADES = (
    ('VSP', 'variacion_permanente_salario'),
    ('VST', 'variacion_transitoria_salario'),
    ('SLN', 'suspension_temporal_contrato'),
    ('IGE', 'incapacidad_general'),
    ('LMA', 'licencia_maternidad'),
    ('VAC', 'vacaciones'),
    ('LR', 'licencia_remunerada'),
    ('AVP', 'aporte_voluntario_pension'),
    ('VCT', 'variacion_centro_trabajo'),
)


def _pesos(valor):
    """La PILA cotiza en pesos enteros: sin decimales."""
    return f'{valor or 0:,.0f}'


def _texto(valor):
    return '' if valor is None else str(valor)


def _novedades(detalle):
    # ING y RET salen del contrato del aporte, como en el plano.
    aporte_contrato = detalle.aporte_contrato
    siglas = ['ING'] if aporte_contrato.ingreso else []
    if aporte_contrato.retiro:
        siglas.append('RET')
    siglas += [sigla for sigla, campo in _NOVEDADES if getattr(detalle, campo)]
    if detalle.dias_incapacidad_laboral:
        siglas.append('IRL')
    return ' · '.join(siglas)


class FormatoAporte:
    """
    Formato del aporte a seguridad social.

    Mismo contrato que `FormatoProgramacion`: `construir()` devuelve los
    flowables y `pdf()` arma el archivo.
    """

    # Un aporte con muchos empleados ocupa varias hojas.
    numerar_paginas = True

    def __init__(self, aporte):
        self.aporte = aporte
        self.estilos = self._estilos()

    def construir(self):
        detalles = (
            HumAporteDetalle.objects.filter(aporte_contrato__aporte=self.aporte)
            .select_related('aporte_contrato__contrato__contacto')
            .order_by('aporte_contrato__contrato__contacto__nombre_corto', 'aporte_contrato_id', 'id')
        )
        return [
            MarcaDocumento(self.aporte.id, self.numerar_paginas),
            *EncabezadoEmpresa(titulo='APORTE A SEGURIDAD SOCIAL').construir(),
            Spacer(1, 0.8 * cm),
            self._datos_aporte(),
            Spacer(1, 0.6 * cm),
            self._tabla_detalles(detalles),
        ]

    def pdf(self):
        """Devuelve `(contenido, nombre)`."""
        buffer = io.BytesIO()
        documento_pdf(buffer, 'Aporte a seguridad social').build(self.construir(), canvasmaker=CanvasNumerado)
        return buffer.getvalue(), f'aporte{self.aporte.id}.pdf'

    @staticmethod
    def _estilos():
        base = getSampleStyleSheet()
        return {
            'dato': ParagraphStyle('dato', parent=base['Normal'], fontSize=9, leading=13),
            'columna': ParagraphStyle(
                'columna', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=7.5, leading=10,
            ),
            'columna_valor': ParagraphStyle(
                'columna_valor', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=7.5, leading=10, alignment=TA_RIGHT,
            ),
            'celda': ParagraphStyle('celda', parent=base['Normal'], fontSize=7.5, leading=10),
        }

    def _datos_aporte(self):
        """Qué aporte es y cuánto suma. En tres columnas, como la programación."""
        aporte = self.aporte
        columnas = (
            [
                f'<b>Código:</b> {aporte.id}',
                f'<b>Periodo:</b> {aporte.anio}-{aporte.mes:02d}',
                f'<b>Periodo salud:</b> {aporte.anio_salud}-{aporte.mes_salud:02d}',
            ],
            [
                f'<b>Sucursal:</b> {_texto(aporte.sucursal.nombre if aporte.sucursal_id else "")}',
                f'<b>Desde:</b> {_texto(aporte.fecha_desde)}',
                f'<b>Hasta:</b> {_texto(aporte.fecha_hasta)}',
            ],
            [
                f'<b>Empleados:</b> {aporte.empleados}',
                f'<b>Líneas:</b> {aporte.lineas}',
                f'<b>Total:</b> {_pesos(aporte.cotizacion_total)}',
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
            Paragraph('Días', estilos['columna_valor']),
            *(Paragraph(titulo, estilos['columna_valor']) for titulo, _ in _COLUMNAS_VALOR),
        ]]
        totales = [Decimal('0')] * len(_COLUMNAS_VALOR)
        for detalle in detalles:
            contacto = detalle.aporte_contrato.contrato.contacto
            empleado = f'{_texto(contacto.numero_identificacion)} - {_texto(contacto.nombre_corto)}'
            novedades = _novedades(detalle)
            if novedades:
                empleado += f'<br/><font size="6.5" color="{_GRIS_NOVEDAD.hexval()}">{novedades}</font>'
            valores = [valor(detalle) or 0 for _, valor in _COLUMNAS_VALOR]
            totales = [total + valor for total, valor in zip(totales, valores)]
            filas.append([
                Paragraph(empleado, estilos['celda']),
                str(detalle.dias_salud),
                *(_pesos(valor) for valor in valores),
            ])
        filas.append([
            Paragraph('<b>Total</b>', estilos['celda']), '',
            *(_pesos(total) for total in totales),
        ])

        tabla = Table(filas, colWidths=_ANCHO_TABLA, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            # Una línea bajo los encabezados y otra sobre el total: se lee sin grilla.
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
            ('LINEABOVE', (0, -1), (-1, -1), 0.6, _GRIS_LINEA),
            ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        return tabla
