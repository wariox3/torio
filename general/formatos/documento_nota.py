"""
Formatos de las notas crédito y débito de venta: la representación gráfica de la
nota electrónica.

Una nota corrige una factura: la crédito le devuelve o le descuenta al cliente, la
débito le cobra algo más (intereses, gastos, un cambio de valor). La hoja es la de
la factura —encabezado, cliente, detalles, impuestos y bloque electrónico con el
QR—, y por eso heredan de `FormatoDocumentoFactura` en vez de copiarla. Cambia lo
que hace de la hoja una nota:

- Qué factura corrige y por qué (el concepto de corrección de la DIAN), en los
  datos del documento.
- El código de la DIAN es el CUDE, no el CUFE, y debajo va el CUFE de la factura
  corregida en lugar de la resolución: una nota no se numera contra una
  resolución, lleva el prefijo fijo de `PREFIJOS_NOTA`.
- No tiene vencimiento: rededoc lo rechaza en una nota.

La factura corregida sale de `documento_referencia`. Si la factura se emitió
por fuera de torio (p. ej. desde itrio) y solo se conocen su prefijo, número y
CUFE, salen de `referencia_prefijo`, `referencia_numero` y `referencia_cue`.
"""
from xml.sax.saxutils import escape

from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

from general.formatos.documento_factura import _ANCHO_PARTES, FormatoDocumentoFactura
from utilidades.numero_letras import valor_en_letras


class FormatoDocumentoNota(FormatoDocumentoFactura):
    """Lo común a las notas de venta: factura corregida, concepto y CUDE."""

    nombre_codigo = 'CUDE'

    @staticmethod
    def _prefijo(documento):
        """El prefijo fijo de la clase de nota, el mismo con que se emite a la DIAN."""
        # Import acá por lo mismo que el logotipo: `general.servicios` importa los
        # formatos, y desde el módulo sería circular.
        from general.servicios.factura_electronica import PREFIJOS_NOTA

        return PREFIJOS_NOTA.get(documento.documento_tipo.documento_clase_id, '')

    # ------------------------------------------------------------ referencia ----

    @staticmethod
    def _factura_referencia(documento):
        """(número con prefijo, fecha, CUFE) de la factura que corrige la nota."""
        referencia = documento.documento_referencia
        if referencia is not None:
            numero = ''
            if referencia.numero is not None:
                prefijo = FormatoDocumentoFactura._prefijo(referencia)
                numero = f'{prefijo}{referencia.numero}'
            return numero, referencia.fecha, referencia.cue
        numero = ''
        if documento.referencia_numero is not None:
            numero = f'{documento.referencia_prefijo or ""}{documento.referencia_numero}'
        return numero, None, documento.referencia_cue

    @staticmethod
    def _concepto(documento):
        concepto = documento.documento_concepto_correccion
        if concepto is None:
            return ''
        return f'{concepto.codigo} - {concepto.nombre}'

    # ---------------------------------------------------------------- partes ----

    def _datos_factura(self, documento, estilos):
        numero, fecha, _ = self._factura_referencia(documento)
        pares = (
            ('FECHA EMISIÓN', self._texto(documento.fecha)),
            ('FACTURA', self._texto(numero)),
            ('FECHA FACTURA', self._texto(fecha)),
            ('CONCEPTO', self._texto(self._concepto(documento))),
            ('MEDIO DE PAGO', self._texto(documento.metodo_pago and documento.metodo_pago.nombre)),
            ('ORDEN DE COMPRA', self._texto(documento.orden_compra)),
        )
        return self._tarjeta(self.titulo_datos, self._filas(pares, estilos), estilos,
                             _ANCHO_PARTES[2])

    # ----------------------------------------------------------- electrónico ----

    def _respaldo_electronico(self, documento, estilos):
        """En vez de la resolución, el CUFE de la factura corregida."""
        _, _, cufe = self._factura_referencia(documento)
        if not cufe:
            return (('CUFE FACTURA', 'Sin referencia a factura electrónica.'),)
        return (('CUFE FACTURA', Paragraph(escape(cufe), estilos['cufe'])),)


class FormatoDocumentoNotaCredito(FormatoDocumentoNota):
    """Nota crédito de venta: le devuelve al cliente, así que no es un cobro."""

    titulo_datos = 'DATOS DE LA NOTA CRÉDITO'
    titulo_electronico = 'REPRESENTACIÓN GRÁFICA DE LA NOTA CRÉDITO ELECTRÓNICA'
    aviso_sin_validar = 'NOTA CRÉDITO SIN VALIDAR ANTE LA DIAN'
    etiqueta_total = 'TOTAL NOTA'

    # El texto libre de la factura le habla al cliente de cómo pagar: en una nota
    # que le devuelve plata diría lo contrario de lo que pasa.
    campo_informacion_superior = None
    campo_informacion_inferior = None

    def _notas(self, documento, configuracion, estilos):
        """Valor en letras y comentarios: sin información de pago."""
        return [
            Paragraph(f'<b>VALOR EN LETRAS:</b> {valor_en_letras(documento.total)}', estilos['texto']),
            Spacer(1, 0.25 * cm),
            Paragraph(f'<b>COMENTARIOS:</b> {self._texto(documento.comentario)}', estilos['texto']),
        ]


class FormatoDocumentoNotaDebito(FormatoDocumentoNota):
    """
    Nota débito de venta: le cobra al cliente algo más, así que conserva lo que la
    factura dice del cobro —información de pago, texto libre de la empresa y
    «TOTAL A PAGAR»—.
    """

    titulo_datos = 'DATOS DE LA NOTA DÉBITO'
    titulo_electronico = 'REPRESENTACIÓN GRÁFICA DE LA NOTA DÉBITO ELECTRÓNICA'
    aviso_sin_validar = 'NOTA DÉBITO SIN VALIDAR ANTE LA DIAN'
