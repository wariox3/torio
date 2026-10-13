"""
Formato del documento soporte en adquisiciones efectuadas a no obligados a facturar.

Es la hoja de la factura vista desde el otro lado: acá la empresa no vende, compra,
y como quien le vende no factura, es ella la que expide el documento. Por eso el
contacto no es el adquiriente sino el vendedor, y lo que la DIAN devuelve al
validarlo no es un CUFE sino un CUDS. El resto —encabezado, detalles, totales,
resolución y QR— se pinta igual, y por eso hereda de `FormatoDocumentoFactura` en
vez de copiarlo.

No lleva el texto libre de la factura de venta (`ven_factura_informacion_*`): ese
texto le habla al cliente —dónde consignar, qué responsabilidades tiene la
empresa—, y en una compra diría lo contrario de lo que pasa.
"""
from general.formatos.documento_factura import FormatoDocumentoFactura


class FormatoDocumentoSoporte(FormatoDocumentoFactura):
    """Documento soporte: vendedor, detalles, totales y bloque electrónico con el CUDS."""

    titulo_datos = 'DATOS DEL DOCUMENTO SOPORTE'
    titulo_contacto = 'VENDEDOR'
    etiqueta_contacto = 'PROVEEDOR'
    nombre_codigo = 'CUDS'
    titulo_electronico = (
        'REPRESENTACIÓN GRÁFICA DEL DOCUMENTO SOPORTE EN ADQUISICIONES EFECTUADAS A '
        'NO OBLIGADOS A FACTURAR'
    )
    aviso_sin_validar = 'DOCUMENTO SOPORTE SIN VALIDAR ANTE LA DIAN'

    campo_informacion_superior = None
    campo_informacion_inferior = None
