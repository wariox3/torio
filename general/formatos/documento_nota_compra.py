"""
Formatos de las notas crédito y débito de compra.

Las notas las expide el proveedor: la crédito le devuelve o le descuenta a la
empresa algo de una compra, la débito le cobra algo más. Lo que torio imprime es
el registro que la empresa hace de ellas, así que no son electrónicas —no tienen
CUDE, QR ni concepto de la DIAN— y el contacto no es un cliente sino el proveedor.

Lo comercial —la empresa, el proveedor, qué se devuelve y cuánto, con sus
impuestos y retenciones— se pinta igual que en la factura, y por eso hereda de
`FormatoDocumentoFactura` en vez de copiarlo. En lugar del bloque electrónico, los
datos del documento dicen qué compra corrige y con qué números la identifica el
proveedor (`soporte`: el de su nota y el de su factura).

Ninguna lleva información de pago: la cuenta bancaria del documento es de la
empresa, y en una compra no es a donde se le paga a nadie.
"""
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

from general.formatos.documento_factura import _ANCHO_PARTES, FormatoDocumentoFactura
from utilidades.formatos import configuracion_actual
from utilidades.numero_letras import valor_en_letras


class FormatoDocumentoNotaCompra(FormatoDocumentoFactura):
    """Lo común a las notas de compra: proveedor, compra corregida, detalles y totales."""

    titulo_contacto = 'PROVEEDOR'
    etiqueta_contacto = 'PROVEEDOR'
    etiqueta_total = 'TOTAL NOTA'

    # El texto libre de la factura de venta le habla al cliente: en una compra
    # diría lo contrario de lo que pasa.
    campo_informacion_superior = None
    campo_informacion_inferior = None

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
        ]

    def _datos_factura(self, documento, estilos):
        compra = documento.documento_referencia
        pares = (
            ('FECHA EMISIÓN', self._texto(documento.fecha)),
            ('SOPORTE', self._texto(documento.soporte)),
            ('COMPRA', self._texto(compra and compra.numero)),
            ('FACTURA PROV.', self._texto(compra and compra.soporte)),
            ('FECHA COMPRA', self._texto(compra and compra.fecha)),
            ('ORDEN DE COMPRA', self._texto(documento.orden_compra)),
        )
        return self._tarjeta(self.titulo_datos, self._filas(pares, estilos), estilos,
                             _ANCHO_PARTES[2])

    def _notas(self, documento, configuracion, estilos):
        """Valor en letras y comentarios, sin información de pago."""
        return [
            Paragraph(f'<b>VALOR EN LETRAS:</b> {valor_en_letras(documento.total)}', estilos['texto']),
            Spacer(1, 0.25 * cm),
            Paragraph(f'<b>COMENTARIOS:</b> {self._texto(documento.comentario)}', estilos['texto']),
        ]


class FormatoDocumentoNotaCreditoCompra(FormatoDocumentoNotaCompra):
    """Nota crédito de compra: el proveedor le devuelve o le descuenta a la empresa."""

    titulo_datos = 'DATOS DE LA NOTA CRÉDITO'


class FormatoDocumentoNotaDebitoCompra(FormatoDocumentoNotaCompra):
    """Nota débito de compra: el proveedor le cobra algo más a la empresa."""

    titulo_datos = 'DATOS DE LA NOTA DÉBITO'
