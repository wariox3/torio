from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from general.formatos.base import FormatoBase
from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import ANCHO_CONTENIDO, anchos

_GRIS_LINEA = colors.HexColor('#9e9e9e')

# Descripción amplia; cantidad, precio y total iguales entre sí.
_ANCHO_TABLA = anchos(0.52, 0.16, 0.16, 0.16)


class FormatoDocumentoGenerico(FormatoBase):
    """
    Impresión genérica de un documento: encabezado de empresa, datos del
    documento, detalles y totales.

    Sirve para cualquier `GenDocumento`. Es el que se usa mientras un tipo no
    tenga un formato propio —una factura electrónica con su CUFE y su QR, una
    remisión sin totales—, y por eso no asume nada del tipo más allá de lo que
    todo documento tiene.

    El encabezado y la caja de la hoja no los decide este formato: salen de
    `utilidades.formatos`, que es lo que hace que un documento impreso y un
    certificado de retención se vean como del mismo sistema.
    """

    def construir(self):
        documento = self.documento
        estilos = self._estilos()

        return [
            *EncabezadoEmpresa(
                titulo=self._titulo(documento),
                # La configuración la busca sola: este formato no la recibe.
            ).construir(),
            Spacer(1, 0.8 * cm),
            self._datos_documento(documento, estilos),
            Spacer(1, 0.6 * cm),
            self._tabla_detalles(documento, estilos),
            Spacer(1, 0.5 * cm),
            self._totales(documento, estilos),
        ]

    @staticmethod
    def _estilos():
        base = getSampleStyleSheet()
        return {
            'dato': ParagraphStyle('dato', parent=base['Normal'], fontSize=9, leading=13),
            'columna': ParagraphStyle(
                'columna', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=8.5, leading=11,
            ),
            'celda': ParagraphStyle('celda', parent=base['Normal'], fontSize=8.5, leading=11),
            'total': ParagraphStyle(
                'total', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=9, alignment=TA_RIGHT, leading=13,
            ),
        }

    @staticmethod
    def _titulo(documento):
        return documento.documento_tipo.nombre.upper()

    def _datos_documento(self, documento, estilos):
        """A quién y cuándo. En dos columnas para no gastar media hoja."""
        contacto = documento.contacto.nombre_corto if documento.contacto_id else ''
        identificacion = (
            documento.contacto.numero_identificacion if documento.contacto_id else ''
        )
        izquierda = [
            f'<b>Contacto:</b> {contacto}',
            f'<b>Identificación:</b> {identificacion}',
        ]
        # El número baja acá: el título de la barra es solo el tipo, pero el
        # número identifica al documento y no puede quedarse fuera de la hoja.
        derecha = [
            f'<b>Número:</b> {documento.numero if documento.numero is not None else "—"}',
            f'<b>Fecha:</b> {documento.fecha or ""}',
            f'<b>Vence:</b> {documento.fecha_vence or ""}',
        ]
        tabla = Table(
            [[
                [Paragraph(texto, estilos['dato']) for texto in izquierda],
                [Paragraph(texto, estilos['dato']) for texto in derecha],
            ]],
            colWidths=[ANCHO_CONTENIDO * 0.6, ANCHO_CONTENIDO * 0.4],
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return tabla

    def _tabla_detalles(self, documento, estilos):
        filas = [[
            Paragraph('Descripción', estilos['columna']),
            Paragraph('Cantidad', estilos['columna']),
            Paragraph('Precio', estilos['columna']),
            Paragraph('Total', estilos['columna']),
        ]]
        for detalle in documento.documentos_detalles_documento_rel.all():
            descripcion = detalle.detalle or (detalle.item.nombre if detalle.item_id else '')
            filas.append([
                Paragraph(descripcion, estilos['celda']),
                f'{detalle.cantidad:,.2f}',
                f'{detalle.precio:,.2f}',
                f'{detalle.total:,.2f}',
            ])

        tabla = Table(filas, colWidths=_ANCHO_TABLA, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            # Una línea bajo los encabezados alcanza para leer la tabla sin
            # encerrar cada celda en una grilla.
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
        ]))
        return tabla

    def _totales(self, documento, estilos):
        """Alineados a la derecha, bajo la columna de totales de la tabla."""
        lineas = (
            ('Subtotal', documento.subtotal),
            ('Descuento', documento.descuento),
            ('Impuesto', documento.impuesto),
            ('Retención', documento.impuesto_retencion),
            ('Total', documento.total),
        )
        filas = [
            [Paragraph(f'{etiqueta}:', estilos['total']),
             Paragraph(f'{valor:,.2f}', estilos['total'])]
            for etiqueta, valor in lineas
        ]
        ancho_etiqueta, ancho_valor = _ANCHO_TABLA[2], _ANCHO_TABLA[3]
        relleno = ANCHO_CONTENIDO - ancho_etiqueta - ancho_valor

        tabla = Table(
            [[''] + fila for fila in filas],
            colWidths=[relleno, ancho_etiqueta, ancho_valor],
        )
        tabla.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (2, 0), (2, -1), 0),
            # El total va separado del resto: es el número que se lee primero.
            ('LINEABOVE', (1, len(filas) - 1), (-1, len(filas) - 1), 0.6, _GRIS_LINEA),
        ]))
        return tabla
