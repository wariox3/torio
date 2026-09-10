"""
Formato del egreso: el comprobante que se firma al girar plata.

No es un documento comercial y por eso no reusa el genérico: no tiene cantidades
ni precios unitarios, sino un asiento a dos columnas. Lo que lleva es lo que hace
falta para autorizar y auditar un giro —a quién, contra qué banco, contra qué
cuentas contables, cuánto en cifras y en letras— y las dos firmas al pie.

El asiento que se imprime incluye la contrapartida del banco, que no es una línea
del documento sino un movimiento que deriva `contabilizar._movimientos_banco`.
Sin ella la hoja mostraría débitos sin créditos y el comprobante no cuadraría a la
vista de quien lo firma. Se calcula acá igual que allá —el banco acredita el total
del egreso—, así que las dos tienen que moverse juntas.
"""
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from general.formatos.base import FormatoBase
from utilidades.formatos import EncabezadoEmpresa
from utilidades.formatos.pagina import ANCHO_CONTENIDO, anchos
from utilidades.numero_letras import valor_en_letras

CERO = Decimal('0')

_GRIS_ETIQUETA = colors.HexColor('#d9d9d9')
_GRIS_LINEA = colors.HexColor('#9e9e9e')

# Etiqueta y valor, dos veces: los datos del egreso caben en cuatro columnas.
_ANCHO_DATOS = anchos(0.19, 0.31, 0.19, 0.31)

# Número del documento afectado, cuenta, contacto, valor y naturaleza. La última
# es una sola letra: no necesita más que el ancho de su encabezado.
_ANCHO_ASIENTO = anchos(0.14, 0.16, 0.45, 0.21, 0.04)


class FormatoDocumentoEgreso(FormatoBase):
    """Comprobante de egreso: datos del giro, su asiento, el valor en letras y las firmas."""

    def construir(self):
        documento = self.documento
        estilos = self._estilos()

        return [
            # El título es el nombre del tipo, igual que en el genérico: el
            # documento se llama como lo llama el sistema, no como lo llame
            # este formato.
            *EncabezadoEmpresa(
                titulo=documento.documento_tipo.nombre.upper(),
            ).construir(),
            Spacer(1, 0.7 * cm),
            self._datos(documento, estilos),
            Spacer(1, 0.5 * cm),
            self._asiento(documento, estilos),
            Spacer(1, 0.4 * cm),
            Paragraph(
                f'<b>VALOR EN LETRAS:</b> {valor_en_letras(documento.total)}',
                estilos['letras'],
            ),
            Spacer(1, 2.2 * cm),
            self._firmas(estilos),
        ]

    @staticmethod
    def _estilos():
        base = getSampleStyleSheet()
        return {
            'etiqueta': ParagraphStyle(
                'etiqueta', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=8, leading=11,
            ),
            'valor': ParagraphStyle('valor', parent=base['Normal'], fontSize=8, leading=11),
            'columna': ParagraphStyle(
                'columna', parent=base['Normal'], fontName='Helvetica-Bold',
                fontSize=7.5, alignment=TA_CENTER, leading=10,
            ),
            'celda': ParagraphStyle('celda', parent=base['Normal'], fontSize=7.5, leading=10),
            'naturaleza': ParagraphStyle(
                'naturaleza', parent=base['Normal'], fontSize=7.5,
                alignment=TA_CENTER, leading=10,
            ),
            'letras': ParagraphStyle('letras', parent=base['Normal'], fontSize=8.5, leading=12),
            'firma': ParagraphStyle(
                'firma', parent=base['Normal'], fontSize=9,
                alignment=TA_CENTER, leading=12,
            ),
        }

    @staticmethod
    def _texto(valor):
        return '' if valor is None else str(valor)

    @staticmethod
    def _moneda(valor):
        return f'{valor or CERO:,.2f}'

    def _datos(self, documento, estilos):
        """
        Los datos del giro, en rejilla de etiqueta y valor.

        Se imprimen todas las filas aunque el dato falte, por lo mismo que el
        encabezado de empresa: el comprobante se firma, y una hoja cuyo alto
        cambia según qué campos estén llenos es más difícil de revisar.
        """
        contacto = documento.contacto
        banco = documento.cuenta_banco

        filas = [
            ('TERCERO', self._texto(contacto and contacto.nombre_corto),
             'NÚMERO', self._texto(documento.numero)),
            ('IDENTIFICACIÓN', self._texto(contacto and contacto.numero_identificacion),
             'FECHA', self._texto(documento.fecha)),
            ('DIRECCIÓN', self._texto(contacto and contacto.direccion),
             'TIPO', self._texto(documento.documento_tipo.nombre)),
            ('SOPORTE', self._texto(documento.soporte),
             'TOTAL', self._moneda(documento.total)),
            ('BANCO', self._texto(banco and banco.nombre),
             'CUENTA', self._texto(banco and banco.numero_cuenta)),
        ]

        datos = [
            [
                Paragraph(etiqueta_1, estilos['etiqueta']),
                Paragraph(valor_1, estilos['valor']),
                Paragraph(etiqueta_2, estilos['etiqueta']),
                Paragraph(valor_2, estilos['valor']),
            ]
            for etiqueta_1, valor_1, etiqueta_2, valor_2 in filas
        ]
        # Los comentarios van a lo ancho: es texto libre y en una celda estrecha
        # se parte en cinco renglones.
        datos.append([
            Paragraph('COMENTARIOS', estilos['etiqueta']),
            Paragraph(self._texto(documento.comentario), estilos['valor']),
            '', '',
        ])

        ultima = len(datos) - 1
        tabla = Table(datos, colWidths=_ANCHO_DATOS)
        tabla.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, _GRIS_LINEA),
            ('BACKGROUND', (0, 0), (0, -1), _GRIS_ETIQUETA),
            ('BACKGROUND', (2, 0), (2, ultima - 1), _GRIS_ETIQUETA),
            ('SPAN', (1, ultima), (3, ultima)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return tabla

    def _lineas_asiento(self, documento):
        """
        Las líneas del documento y, si hace falta, la contrapartida del banco.

        Hay egresos de dos formas. Unos traen solo lo que se paga y el banco es
        una pata que no está en los detalles: la genera
        `contabilizar._movimientos_banco` acreditando el total del documento.
        Otros ya traen el asiento completo, banco incluido, y entonces sus
        líneas cuadran solas y el total queda en cero.

        Por eso la contrapartida se agrega solo cuando el total no es cero, que
        es exactamente cuando `_movimientos_banco` aporta algo. Agregarla siempre
        metería una fila de 0,00 en los documentos de la segunda forma.
        """
        lineas = []
        for detalle in documento.documentos_detalles_documento_rel.all():
            debita = detalle.naturaleza != 'C'
            lineas.append({
                # El documento que cruza esta línea: en un egreso es la factura
                # que se está pagando, y es el dato por el que se busca el
                # comprobante cuando alguien reclama un pago.
                'numero': self._texto(
                    detalle.documento_afectado and detalle.documento_afectado.numero
                ),
                'codigo': detalle.cuenta.codigo if detalle.cuenta_id else '',
                'contacto': detalle.contacto.nombre_corto if detalle.contacto_id else '',
                'valor': detalle.precio,
                'naturaleza': 'D' if debita else 'C',
            })

        if documento.total:
            banco = documento.cuenta_banco
            cuenta_banco = banco.cuenta if banco and banco.cuenta_id else None
            lineas.append({
                'numero': '',
                'codigo': cuenta_banco.codigo if cuenta_banco else '',
                'contacto': self._texto(banco and banco.nombre),
                'valor': documento.total,
                'naturaleza': 'C',
            })
        return lineas

    def _asiento(self, documento, estilos):
        """
        El asiento en una sola columna de valor, con la naturaleza al lado.

        Dos columnas de débito y crédito dejan media tabla en ceros: cada línea
        cae de un lado solo. Con `VALOR` y una `N` de una letra se ve lo mismo en
        la mitad del ancho, y lo que sobra se lo lleva el nombre de la cuenta,
        que es lo que se estaba partiendo en dos renglones.

        El pie suma solo los débitos: en un asiento cuadrado esa es la plata que
        se giró, y sumar la columna entera daría débitos más créditos, que es el
        doble del comprobante y no significa nada.
        """
        encabezados = ('NÚMERO', 'CUENTA', 'CONTACTO', 'VALOR', 'N')
        filas = [[Paragraph(texto, estilos['columna']) for texto in encabezados]]

        total = CERO
        for linea in self._lineas_asiento(documento):
            if linea['naturaleza'] == 'D':
                total += linea['valor']
            filas.append([
                Paragraph(linea['numero'], estilos['celda']),
                Paragraph(linea['codigo'], estilos['celda']),
                Paragraph(linea['contacto'], estilos['celda']),
                self._moneda(linea['valor']),
                Paragraph(linea['naturaleza'], estilos['naturaleza']),
            ])

        ultimo_renglon = len(filas) - 1
        filas.append(['', '', 'TOTAL', self._moneda(total), ''])

        tabla = Table(filas, colWidths=_ANCHO_ASIENTO, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('BACKGROUND', (0, 0), (-1, 0), _GRIS_ETIQUETA),
            ('GRID', (0, 0), (-1, ultimo_renglon), 0.5, _GRIS_LINEA),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
            ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('FONTNAME', (2, -1), (3, -1), 'Helvetica-Bold'),
            ('LINEABOVE', (2, -1), (3, -1), 0.6, _GRIS_LINEA),
        ]))
        return tabla

    @staticmethod
    def _firmas(estilos):
        """Quien recibe y quien autoriza. Es lo que convierte la hoja en un comprobante."""
        ancho = ANCHO_CONTENIDO / 2
        tabla = Table(
            [[Paragraph('Beneficiario', estilos['firma']),
              Paragraph('Responsable', estilos['firma'])]],
            colWidths=[ancho, ancho],
        )
        tabla.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (0, 0), 0.6, colors.black),
            ('LINEABOVE', (1, 0), (1, 0), 0.6, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 1.5 * cm),
            ('RIGHTPADDING', (0, 0), (-1, -1), 1.5 * cm),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        return tabla
