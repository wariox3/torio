"""
Estado de situación financiera en PDF.

Es la hoja que se firma y se entrega —a la gerencia, al banco, a la asamblea—,
así que sigue la presentación de un estado financiero colombiano: la fecha de
los cortes en letras, «cifras expresadas en pesos colombianos», negativos entre
paréntesis, subtotales con una línea, totales con doble subrayado y, al pie, las
firmas del representante legal, el contador y el revisor fiscal.

Las firmas van en blanco: los nombres y las tarjetas profesionales no están en
`GenConfiguracion`, y en papel se firman a mano.
"""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from contabilidad.servicios import situacion_financiera as sf
from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import anchos, documento_pdf

_MESES = (
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
)
_NEGRO = colors.HexColor('#15232a')
_GRIS = colors.HexColor('#5d6e76')
_TEAL = colors.HexColor('#0d6b7a')
_FONDO_FINAL = colors.HexColor('#e6f6f9')

# Con comparativo: concepto, los dos cortes, la variación y el %. Sin él, el
# concepto se queda con el espacio.
_ANCHOS_COMPARADO = anchos(0.40, 0.165, 0.165, 0.165, 0.105)
_ANCHOS_SOLO = anchos(0.70, 0.30)

_FIRMAS = (('Representante legal', 'C.C.'), ('Contador público', 'T.P.'), ('Revisor fiscal', 'T.P.'))


def _fecha_larga(fecha):
    return f'{fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}'


def _importe(valor):
    if valor is None:
        return ''
    # Se redondea antes de decidir el signo: unos centavos negativos no son «(0)».
    valor = round(valor)
    if valor < 0:
        return f'({abs(valor):,})'
    return f'{valor:,}'


def _porcentaje(valor):
    return '' if valor is None else f'{valor * 100:,.1f} %'


def _estilos():
    base = getSampleStyleSheet()
    return {
        'periodo': ParagraphStyle(
            'periodo', parent=base['Normal'], fontSize=9.5, leading=13, alignment=TA_CENTER,
        ),
        'moneda': ParagraphStyle(
            'moneda', parent=base['Normal'], fontName='Helvetica-Oblique', fontSize=8.5,
            leading=11, alignment=TA_CENTER, textColor=_GRIS,
        ),
        'pie': ParagraphStyle(
            'pie', parent=base['Normal'], fontSize=8, leading=10, textColor=_GRIS,
        ),
        'firma': ParagraphStyle(
            'firma', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11,
        ),
        'documento': ParagraphStyle(
            'documento', parent=base['Normal'], fontSize=8, leading=10, textColor=_GRIS,
        ),
    }


def _estilo_concepto(tipo, _cache={}):
    """
    El concepto va en un `Paragraph` para que un nombre largo parta en dos
    líneas en lugar de montarse sobre la columna de importes. La sangría marca
    el nivel: sección, subsección y subtotal, línea.
    """
    if tipo not in _cache:
        negrita = tipo not in (sf.LINEA, sf.RESULTADO)
        _cache[tipo] = ParagraphStyle(
            f'concepto_{tipo}', parent=getSampleStyleSheet()['Normal'],
            fontName='Helvetica-Bold' if negrita else 'Helvetica', fontSize=8.5, leading=10.5,
            textColor=_TEAL if tipo == sf.SUBSECCION else _NEGRO,
            leftIndent={sf.LINEA: 16, sf.RESULTADO: 16, sf.SUBSECCION: 8, sf.SUBTOTAL: 8}.get(tipo, 0),
        )
    return _cache[tipo]


class FormatoSituacionFinanciera:
    """Mismo contrato que `FormatoCertificadoRetencion`: `pdf()` da `(contenido, nombre)`."""

    def __init__(self, filas, configuracion, fecha_corte, fecha_anterior):
        self.filas = filas
        self.configuracion = configuracion
        self.fecha_corte = fecha_corte
        self.fecha_anterior = fecha_anterior
        self.estilos = _estilos()

    def pdf(self):
        buffer = io.BytesIO()
        documento_pdf(buffer, 'Estado de situación financiera').build(self.construir())
        return buffer.getvalue(), f'estado_situacion_financiera_{self.fecha_corte}.pdf'

    def construir(self):
        periodo = f'A {_fecha_larga(self.fecha_corte)}'
        if self.fecha_anterior is not None:
            periodo += f' y {_fecha_larga(self.fecha_anterior)}'
        return [
            *EncabezadoEmpresa(
                self.configuracion, titulo='ESTADO DE SITUACIÓN FINANCIERA',
            ).construir(),
            Spacer(1, 0.5 * cm),
            Paragraph(periodo, self.estilos['periodo']),
            Paragraph('Cifras expresadas en pesos colombianos', self.estilos['moneda']),
            Spacer(1, 0.5 * cm),
            self._tabla(),
            Spacer(1, 0.4 * cm),
            Paragraph(
                'El resultado del ejercicio incluye las cuentas de resultado (clases 4 a 7) '
                'que a la fecha de corte no se han cerrado.',
                self.estilos['pie'],
            ),
            Spacer(1, 2.2 * cm),
            KeepTogether(self._firmas()),
        ]

    def _tabla(self):
        comparado = self.fecha_anterior is not None
        encabezado = ['', self.fecha_corte.strftime('%d/%m/%Y')]
        if comparado:
            encabezado += [self.fecha_anterior.strftime('%d/%m/%Y'), 'Variación', '%']
        datos = [encabezado]
        estilo = [
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('TEXTCOLOR', (0, 0), (-1, -1), _NEGRO),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (-1, 0), _GRIS),
            ('LINEBELOW', (0, 0), (-1, 0), 0.8, _NEGRO),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ]
        for fila in self.filas:
            tipo = fila['tipo']
            if tipo in (sf.SECCION, sf.TOTAL_FINAL):
                datos.append([''] * len(encabezado))
            nombre = escape(fila['nombre'])
            if tipo in (sf.SECCION, sf.TOTAL, sf.TOTAL_FINAL):
                nombre = nombre.upper()
            if tipo == sf.LINEA and fila['codigo']:
                nombre = f'{fila["codigo"]}&nbsp;&nbsp;{nombre}'
            linea = [Paragraph(nombre, _estilo_concepto(tipo)), _importe(fila['actual'])]
            if comparado:
                linea += [_importe(fila['anterior']), _importe(fila['variacion']),
                          _porcentaje(fila['porcentaje'])]
            datos.append(linea)

            r = len(datos) - 1
            if tipo not in (sf.LINEA, sf.RESULTADO):
                estilo.append(('FONTNAME', (0, r), (-1, r), 'Helvetica-Bold'))
            if tipo == sf.SUBTOTAL:
                estilo.append(('LINEABOVE', (1, r), (-1, r), 0.5, _NEGRO))
            if tipo in (sf.TOTAL, sf.TOTAL_FINAL):
                estilo += [
                    ('LINEABOVE', (1, r), (-1, r), 0.5, _NEGRO),
                    # Doble subrayado: dos líneas finas casi juntas.
                    ('LINEBELOW', (1, r), (-1, r), 0.5, _NEGRO, None, None, 1, 2, 1.2),
                    ('TOPPADDING', (0, r), (-1, r), 4),
                    ('BOTTOMPADDING', (0, r), (-1, r), 4),
                ]
            if tipo == sf.TOTAL_FINAL:
                estilo.append(('BACKGROUND', (0, r), (-1, r), _FONDO_FINAL))

        tabla = Table(datos, colWidths=_ANCHOS_COMPARADO if comparado else _ANCHOS_SOLO, repeatRows=1)
        tabla.setStyle(TableStyle(estilo))
        return tabla

    def _firmas(self):
        celdas = [
            [Paragraph(cargo, self.estilos['firma']), Paragraph(documento, self.estilos['documento'])]
            for cargo, documento in _FIRMAS
        ]
        # Columnas vacías entre firmas, para que las tres líneas no se toquen.
        fila = [celdas[0], '', celdas[1], '', celdas[2]]
        tabla = Table([fila], colWidths=anchos(0.28, 0.08, 0.28, 0.08, 0.28))
        tabla.setStyle(TableStyle([
            *(('LINEABOVE', (c, 0), (c, 0), 0.6, _NEGRO) for c in (0, 2, 4)),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        return [tabla]
