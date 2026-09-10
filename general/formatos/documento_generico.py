from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from general.servicios.formatos.base import FormatoBase


class FormatoGenerico(FormatoBase):
    """Formato genérico: encabezado, tabla de detalles y totales."""

    def construir(self):
        documento = self.documento
        estilos = getSampleStyleSheet()
        elementos = []

        # Encabezado: tipo + número, contacto y fecha.
        elementos.append(
            Paragraph(f'{documento.documento_tipo.nombre} N° {documento.numero or "—"}', estilos['Title'])
        )
        contacto = documento.contacto.nombre_corto if documento.contacto_id else ''
        elementos.append(Paragraph(f'Contacto: {contacto}', estilos['Normal']))
        elementos.append(Paragraph(f'Fecha: {documento.fecha or ""}', estilos['Normal']))
        elementos.append(Spacer(1, 0.5 * cm))

        # Tabla de detalles.
        filas = [['Descripción', 'Cantidad', 'Precio', 'Total']]
        for detalle in documento.documentos_detalles_documento_rel.all():
            descripcion = detalle.detalle or (detalle.item.nombre if detalle.item_id else '')
            filas.append([
                descripcion,
                f'{detalle.cantidad:,.2f}',
                f'{detalle.precio:,.2f}',
                f'{detalle.total:,.2f}',
            ])
        tabla = Table(filas, colWidths=[9 * cm, 3 * cm, 3 * cm, 3 * cm])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#cccccc')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 0.5 * cm))

        # Totales.
        elementos.append(Paragraph(f'Subtotal: {documento.subtotal:,.2f}', estilos['Normal']))
        elementos.append(Paragraph(f'Descuento: {documento.descuento:,.2f}', estilos['Normal']))
        elementos.append(Paragraph(f'Impuesto: {documento.impuesto:,.2f}', estilos['Normal']))
        elementos.append(Paragraph(f'Total: {documento.total:,.2f}', estilos['Heading2']))

        return elementos
