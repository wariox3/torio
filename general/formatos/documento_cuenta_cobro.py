"""
Formato de la cuenta de cobro.

Es la factura de venta sin lo electrónico: la cuenta de cobro la expide quien no
está obligado a facturar, así que no tiene CUFE, ni QR, ni resolución de la DIAN
que mostrar. Lo comercial —la empresa, el cliente, qué se cobra y cuánto— se pinta
igual que en la factura, y por eso hereda de `FormatoDocumentoFactura` en vez de
copiarlo: un cambio en el encabezado o en los detalles le llega a las dos hojas.

En lugar del bloque electrónico lleva las firmas al pie, como en itrio: quien la
elaboró y el cliente que la acepta. Sin CUFE que la respalde, la aceptación
firmada es lo que hace de la hoja un cobro.
"""
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import CondPageBreak, Paragraph, Spacer, Table, TableStyle

from general.formatos.documento_factura import FormatoDocumentoFactura
from utilidades.formatos import configuracion_actual
from utilidades.formatos.pagina import anchos

# Las dos firmas, con un hueco entre ellas.
_ANCHO_FIRMAS = anchos(0.42, 0.06, 0.52)
# El espacio en blanco sobre la línea, donde va la firma.
_ALTO_FIRMA = 1.6 * cm


class FormatoDocumentoCuentaCobro(FormatoDocumentoFactura):
    """Cuenta de cobro: partes, detalles, totales y las firmas al pie."""

    titulo_datos = 'DATOS DE LA CUENTA DE COBRO'

    def construir(self):
        documento = self.documento
        estilos = self._estilos()
        configuracion = configuracion_actual()

        return [
            self._encabezado(documento, configuracion, estilos),
            Spacer(1, 0.3 * cm),
            self._partes(documento, estilos),
            Spacer(1, 0.5 * cm),
            self._detalles(documento, estilos),
            Spacer(1, 0.4 * cm),
            self._resumen(documento, configuracion, estilos),
            # Las firmas no se separan de la hoja que firman: si no caben, pasan
            # juntas a la siguiente en vez de quedar partidas.
            CondPageBreak(_ALTO_FIRMA + 1.5 * cm),
            Spacer(1, _ALTO_FIRMA),
            self._firmas(estilos),
        ]

    @classmethod
    def _estilos(cls):
        estilos = super()._estilos()
        estilos['firma'] = ParagraphStyle(
            'cuenta_cobro_firma', parent=estilos['etiqueta'], alignment=TA_CENTER,
        )
        return estilos

    @staticmethod
    def _firmas(estilos):
        """Quien la elaboró, a la izquierda; la aceptación del cliente, a la derecha."""
        tabla = Table(
            [[Paragraph('ELABORADO POR', estilos['firma']), '',
              Paragraph('ACEPTADA, FIRMADA Y/O SELLO Y FECHA', estilos['firma'])]],
            colWidths=_ANCHO_FIRMAS,
        )
        tabla.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (0, 0), 0.6, colors.black),
            ('LINEABOVE', (2, 0), (2, 0), 0.6, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        return tabla
