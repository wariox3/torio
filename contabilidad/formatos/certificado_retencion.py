"""
Certificado de retención en PDF.

Un certificado es por tercero, pero el informe que lo alimenta
(`balance.certificado_retencion`) sale plano: una fila por cuenta y tercero,
ordenada por cuenta. Acá se agrupa al revés —por tercero, y dentro de él una
línea por cuenta— porque eso es lo que se firma y se entrega: cada tercero
recibe su propia hoja con lo que se le retuvo en el rango.

El texto legal no es decorativo. El artículo 381 del Estatuto Tributario obliga a
expedir el certificado, y el artículo 10 del Decreto 836 de 1991 es el que
permite entregarlo sin firma autógrafa; sin esa segunda mención el documento
impreso no se sostiene solo.
"""
from decimal import Decimal

import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from rest_framework.exceptions import ValidationError

from contabilidad.servicios.balance import RETENCION
from utilidades.formatos import EncabezadoEmpresa, datos_empresa
from utilidades.formatos.pagina import anchos, documento_pdf

CERO = Decimal('0')

# Concepto se lleva algo más de la mitad; las dos columnas de importes van
# iguales. Como fracciones del ancho útil y no en centímetros, para que la
# tabla no se pase del marco cuando cambien los márgenes.
_ANCHO_TABLA = anchos(0.55, 0.225, 0.225)
_GRIS_LINEA = colors.HexColor('#9e9e9e')

_TEXTO_LEGAL = (
    'Se expide este certificado en cumplimiento de lo establecido en el '
    'Artículo 381 del Estatuto Tributario. Este certificado no requiere firma '
    'autógrafa de acuerdo con el artículo 10 del Decreto Reglamentario 836 de 1991.'
)


def _estilos():
    base = getSampleStyleSheet()
    return {
        'parrafo': ParagraphStyle(
            'parrafo', parent=base['Normal'], fontSize=9.5,
            alignment=TA_JUSTIFY, leading=15,
        ),
        'legal': ParagraphStyle(
            'legal', parent=base['Normal'], fontSize=8.5,
            alignment=TA_JUSTIFY, leading=13,
        ),
        'columna': ParagraphStyle(
            'columna', parent=base['Normal'], fontName='Helvetica-Bold',
            fontSize=8.5, alignment=TA_CENTER, leading=11,
        ),
        'concepto': ParagraphStyle(
            'concepto', parent=base['Normal'], fontSize=8.5, leading=11,
        ),
    }


def _moneda(valor):
    """
    `$1,234.56`, con el signo delante del peso y no entre él y el número.

    Un valor negativo es una retención reversada en el rango, así que sale y no
    se esconde; `$-1,234.56` se lee como si el signo fuera parte del importe.
    """
    valor = valor or CERO
    if valor < 0:
        return f'-${abs(valor):,.2f}'
    return f'${valor:,.2f}'


def _texto(valor):
    return '' if valor is None else str(valor)


def _agrupar_por_tercero(filas):
    """
    Un certificado por tercero, conservando el orden por cuenta de cada uno.

    El informe llega ordenado por código de cuenta, así que un mismo tercero
    aparece salteado entre cuentas. Se agrupa por `contacto_id` sin reordenar las
    líneas dentro del grupo, para que el certificado siga el mismo orden que el
    informe en pantalla.

    Los movimientos sin tercero se descartan. En el informe son una fila legítima
    —una retención cuya cuenta no exige contacto—, pero un certificado se expide
    *a alguien*: sin tercero no hay a quién certificarle ni a quién entregárselo,
    y agrupados bajo `None` saldrían como una hoja dirigida a nadie.
    """
    terceros = {}
    for fila in filas:
        if fila.get('tipo') != RETENCION or fila.get('contacto_id') is None:
            continue
        terceros.setdefault(fila['contacto_id'], []).append(fila)
    return terceros


def _declaracion(lineas, configuracion, fecha_desde, fecha_hasta, estilos):
    """El párrafo que dice a quién, cuándo y dónde se le retuvo."""
    primera = lineas[0]
    contacto = _texto(primera.get('contacto')) or 'el tercero'
    identificacion = _texto(primera.get('identificacion'))
    ciudad = datos_empresa(configuracion)['ciudad']

    lugar = f' en la ciudad de {ciudad}' if ciudad else ''
    nit = f' con NIT: <b>{identificacion}</b>' if identificacion else ''
    return Paragraph(
        f'Durante el año gravable {fecha_hasta.year}, desde el {fecha_desde} hasta '
        f'el {fecha_hasta}, practicó{lugar} las siguientes retenciones a '
        f'<b>{contacto}</b>{nit}',
        estilos['parrafo'],
    )


def _tabla(lineas, estilos):
    """Una línea por cuenta, con el total al pie."""
    filas = [[
        Paragraph('Concepto', estilos['columna']),
        Paragraph('Monto sujeto a retención ($)', estilos['columna']),
        Paragraph('Retenido y consignado ($)', estilos['columna']),
    ]]
    total_base = total_retenido = CERO
    for linea in lineas:
        base = linea.get('base_retenido') or CERO
        retenido = linea.get('retenido') or CERO
        total_base += base
        total_retenido += retenido
        filas.append([
            Paragraph(_texto(linea.get('nombre')), estilos['concepto']),
            _moneda(base),
            _moneda(retenido),
        ])
    filas.append(['', _moneda(total_base), _moneda(total_retenido)])

    ultima = len(filas) - 1
    tabla = Table(filas, colWidths=_ANCHO_TABLA, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        # Una línea bajo los encabezados y otra sobre el total: alcanza para leer
        # la tabla sin encerrar cada celda en una grilla.
        ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
        ('LINEABOVE', (0, ultima), (-1, ultima), 0.6, _GRIS_LINEA),
        ('FONTNAME', (0, ultima), (-1, ultima), 'Helvetica-Bold'),
    ]))
    return tabla


class FormatoCertificadoRetencion:
    """
    Formato del certificado de retención.

    Mismo contrato que los formatos de `general`: `construir()` devuelve los
    flowables y el que imprime arma el PDF. No hereda de `FormatoBase` porque
    aquel recibe un documento y este recibe las filas de un informe con el rango
    que las produjo, que es de donde sale la declaración del párrafo.
    """

    def __init__(self, filas, configuracion, fecha_desde, fecha_hasta):
        self.filas = filas
        self.configuracion = configuracion
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self.estilos = _estilos()

    def construir(self):
        """Los flowables del PDF completo: una hoja por tercero."""
        terceros = _agrupar_por_tercero(self.filas)
        if not terceros:
            raise ValidationError(
                'No hay retenciones con tercero para certificar en el rango.'
            )
        elementos = []
        for indice, lineas in enumerate(terceros.values()):
            if indice:
                elementos.append(PageBreak())
            elementos.extend(self._hoja(lineas))
        return elementos

    def pdf(self):
        """Devuelve `(contenido, nombre)`."""
        buffer = io.BytesIO()
        documento_pdf(buffer, 'Certificado de retención').build(self.construir())
        return buffer.getvalue(), f'certificado_retencion{self.fecha_desde}.pdf'

    def _hoja(self, lineas):
        """La hoja de un tercero."""
        return [
            *EncabezadoEmpresa(
                self.configuracion, titulo='CERTIFICADO DE RETENCIÓN',
            ).construir(),
            Spacer(1, 1.1 * cm),
            _declaracion(
                lineas, self.configuracion,
                self.fecha_desde, self.fecha_hasta, self.estilos,
            ),
            Spacer(1, 1.1 * cm),
            _tabla(lineas, self.estilos),
            Spacer(1, 1.1 * cm),
            Paragraph(_TEXTO_LEGAL, self.estilos['legal']),
        ]
