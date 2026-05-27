from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

EMISOR = {
    'nombre': 'Torio SAS',
    'nit': '901.000.000-1',
    'direccion': 'Cra 7 #12-34',
    'ciudad': 'Bogotá, Colombia',
    'telefono': '+57 300 000 0000',
    'correo': 'facturacion@torio.com',
}

TINTA = colors.HexColor('#111111')
GRIS = colors.HexColor('#6B6B6B')
LINEA = colors.HexColor('#E5E5E5')


def _formato_moneda(valor):
    if valor is None:
        return '$0'
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    entero, decimales = f'{valor:.2f}'.split('.')
    entero_fmt = f'{int(entero):,}'.replace(',', '.')
    return f'${entero_fmt},{decimales}'


def _estilos():
    return {
        'marca': ParagraphStyle(
            'marca', fontName='Helvetica-Bold', fontSize=20,
            textColor=TINTA, leading=24, alignment=TA_LEFT,
        ),
        'titulo': ParagraphStyle(
            'titulo', fontName='Helvetica-Bold', fontSize=20,
            textColor=TINTA, leading=24, alignment=TA_RIGHT,
        ),
        'etiqueta': ParagraphStyle(
            'etiqueta', fontName='Helvetica', fontSize=8,
            textColor=GRIS, leading=11, alignment=TA_LEFT,
            spaceAfter=2,
        ),
        'etiqueta_der': ParagraphStyle(
            'etiqueta_der', fontName='Helvetica', fontSize=8,
            textColor=GRIS, leading=11, alignment=TA_RIGHT,
        ),
        'valor': ParagraphStyle(
            'valor', fontName='Helvetica', fontSize=10,
            textColor=TINTA, leading=13, alignment=TA_LEFT,
        ),
        'valor_der': ParagraphStyle(
            'valor_der', fontName='Helvetica', fontSize=10,
            textColor=TINTA, leading=13, alignment=TA_RIGHT,
        ),
        'total': ParagraphStyle(
            'total', fontName='Helvetica-Bold', fontSize=14,
            textColor=TINTA, leading=18, alignment=TA_RIGHT,
        ),
        'pie': ParagraphStyle(
            'pie', fontName='Helvetica', fontSize=8,
            textColor=GRIS, leading=11, alignment=TA_LEFT,
        ),
    }


def _bloque_partes(estilos, movimiento):
    contacto = movimiento.contacto
    cliente = movimiento.cliente

    receptor_lineas = [
        f'<b>{contacto.nombre_corto}</b>',
        f'{contacto.identificacion.nombre if contacto.identificacion_id else ""} {contacto.numero_identificacion}'.strip(),
        contacto.direccion or '',
        contacto.ciudad.nombre if contacto.ciudad_id else '',
        contacto.correo or '',
    ]
    if cliente:
        receptor_lineas.append(f'Cliente: {cliente.nombre}')

    emisor_html = (
        f'<b>{EMISOR["nombre"]}</b><br/>'
        f'NIT {EMISOR["nit"]}<br/>'
        f'{EMISOR["direccion"]}<br/>'
        f'{EMISOR["ciudad"]}<br/>'
        f'{EMISOR["telefono"]}<br/>'
        f'{EMISOR["correo"]}'
    )
    receptor_html = '<br/>'.join(linea for linea in receptor_lineas if linea)

    tabla = Table(
        [
            [Paragraph('DE', estilos['etiqueta']), Paragraph('PARA', estilos['etiqueta'])],
            [Paragraph(emisor_html, estilos['valor']), Paragraph(receptor_html, estilos['valor'])],
        ],
        colWidths=['50%', '50%'],
    )
    tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 4),
    ]))
    return tabla


def _bloque_encabezado(estilos, movimiento):
    fecha = movimiento.fecha.strftime('%d/%m/%Y') if movimiento.fecha else ''
    vence = movimiento.fecha_vence.strftime('%d/%m/%Y') if movimiento.fecha_vence else '—'
    numero = f'FAC-{movimiento.id:06d}'

    meta_html = (
        f'<font color="#6B6B6B" size="8">N° FACTURA</font><br/>'
        f'<font size="11"><b>{numero}</b></font><br/><br/>'
        f'<font color="#6B6B6B" size="8">FECHA</font><br/>'
        f'<font size="10">{fecha}</font><br/><br/>'
        f'<font color="#6B6B6B" size="8">VENCE</font><br/>'
        f'<font size="10">{vence}</font>'
    )

    tabla = Table(
        [[Paragraph(EMISOR['nombre'].upper(), estilos['marca']),
          Paragraph('FACTURA', estilos['titulo'])],
         ['', Paragraph(meta_html, estilos['valor_der'])]],
        colWidths=['50%', '50%'],
    )
    tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('SPAN', (0, 0), (0, 1)),
    ]))
    return tabla


def _bloque_detalle(estilos, movimiento):
    valor = movimiento.valor or Decimal('0')
    filas = [
        [Paragraph('CONCEPTO', estilos['etiqueta']),
         Paragraph('VALOR', estilos['etiqueta_der'])],
        [Paragraph(movimiento.concepto or '', estilos['valor']),
         Paragraph(_formato_moneda(valor), estilos['valor_der'])],
    ]
    tabla = Table(filas, colWidths=['75%', '25%'])
    tabla.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, LINEA),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, LINEA),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return tabla


def _bloque_totales(estilos, movimiento):
    valor = movimiento.valor or Decimal('0')
    filas = [
        [Paragraph('Subtotal', estilos['etiqueta_der']),
         Paragraph(_formato_moneda(valor), estilos['valor_der'])],
        [Paragraph('Total', estilos['etiqueta_der']),
         Paragraph(_formato_moneda(valor), estilos['total'])],
    ]
    tabla = Table(filas, colWidths=['70%', '30%'], hAlign='RIGHT')
    tabla.setStyle(TableStyle([
        ('LINEABOVE', (0, -1), (-1, -1), 1.2, TINTA),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return tabla


def _bloque_pie(estilos, movimiento):
    evento = movimiento.evento_pago
    if evento is None:
        return Paragraph(
            'Gracias por su pago. Documento generado electrónicamente.',
            estilos['pie'],
        )
    metodo = (evento.metodo_pago or 'pago electrónico').replace('_', ' ').title()
    ref = evento.referencia or evento.transaccion or ''
    estado = (evento.estado or '').title()
    pie_html = (
        f'Pagado vía Wompi · {metodo} · Estado: {estado}<br/>'
        f'Referencia: {ref}<br/><br/>'
        'Documento generado electrónicamente por Torio.'
    )
    return Paragraph(pie_html, estilos['pie'])


def generar_factura_pdf(movimiento):
    """
    Devuelve los bytes del PDF de la factura para un CtnMovimiento.
    Diseño minimalista monocromático con Platypus. Listo para mezclar
    con canvas.drawString(x, y, ...) si más adelante se requieren
    secciones con posicionamiento absoluto.
    """
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f'Factura FAC-{movimiento.id:06d}',
        author=EMISOR['nombre'],
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id='cuerpo', showBoundary=0,
    )
    doc.addPageTemplates([PageTemplate(id='principal', frames=[frame])])

    estilos = _estilos()
    historia = [
        _bloque_encabezado(estilos, movimiento),
        Spacer(1, 14 * mm),
        _bloque_partes(estilos, movimiento),
        Spacer(1, 12 * mm),
        _bloque_detalle(estilos, movimiento),
        Spacer(1, 6 * mm),
        _bloque_totales(estilos, movimiento),
        Spacer(1, 14 * mm),
        _bloque_pie(estilos, movimiento),
    ]
    doc.build(historia)
    return buffer.getvalue()
