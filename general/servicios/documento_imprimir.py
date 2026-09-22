import io
import re
import unicodedata
import zipfile

from reportlab.platypus import PageBreak
from rest_framework.exceptions import ValidationError

from general.formatos import (
    FormatoDocumentoEgreso, FormatoDocumentoFactura, FormatoDocumentoGenerico,
    FormatoDocumentoPago,
)
from general.models.documento import DOCUMENTO_TIPO_FACTURA_VENTA
from utilidades.formatos.pagina import CanvasNumerado, MarcaDocumento, documento_pdf

# Qué formato imprime cada tipo de documento. Está quemado a propósito y no sale
# de `GenDocumentoTipo.formato`: mientras sean pocos los tipos con formato propio,
# una columna configurable obliga a sembrarla en cada tenant y a mantenerla en el
# fixture para que el egreso y el pago salgan bien, y basta que alguien la edite
# para que un comprobante se imprima con el formato equivocado.
#
# El día que sean muchos, esto pasa a ser un mapa por tipo o vuelve a la columna;
# el punto de entrada —`_clase_formato`— no cambia.
DOCUMENTO_TIPO_PAGO = 4  # mismo id que `contabilizar.DOCUMENTO_TIPO_PAGO`
DOCUMENTO_TIPO_EGRESO = 8  # mismo id que `contabilizar.DOCUMENTO_TIPO_EGRESO`

FORMATOS = {
    DOCUMENTO_TIPO_FACTURA_VENTA: FormatoDocumentoFactura,
    DOCUMENTO_TIPO_PAGO: FormatoDocumentoPago,
    DOCUMENTO_TIPO_EGRESO: FormatoDocumentoEgreso,
}


def _clase_formato(documento):
    """La clase de formato del documento. El genérico sirve para cualquiera."""
    return FORMATOS.get(documento.documento_tipo_id, FormatoDocumentoGenerico)


def _construir(documento):
    """
    Elige la clase de formato según el tipo y devuelve los elementos del documento.

    Todos arrancan con su `MarcaDocumento`, numeren o no: es la marca la que le dice
    al canvas dónde termina el documento anterior, así que uno sin numerar que no
    la llevara le sumaría sus páginas al que va antes.
    """
    clase = _clase_formato(documento)
    return [MarcaDocumento(documento.id, clase.numerar_paginas), *clase(documento).construir()]


def _nombre_archivo(documento, sufijo=''):
    """
    El nombre del PDF: el tipo de documento en minúsculas, seguido del número.

    Sin tildes, sin espacios y sin mayúsculas —«FACTURA ELECTRÓNICA DE VENTA»
    N° 2799 queda como `factura_electronica_de_venta2799.pdf`—. No es cosmética:
    el nombre viaja en la cabecera `Content-Disposition`, y los acentos y los
    espacios obligan a codificarlo o quedan a merced de cómo lo interprete cada
    navegador y cada sistema de archivos.

    Un documento sin numerar cae en su id, para que el archivo siga siendo
    distinguible.
    """
    numero = documento.numero if documento.numero is not None else documento.id
    return f'{_normalizar(documento.documento_tipo.nombre)}{numero}{sufijo}.pdf'


def _normalizar(texto):
    """Minúsculas, sin tildes y con guion bajo en lugar de lo que no sea alfanumérico."""
    sin_tildes = ''.join(
        caracter for caracter in unicodedata.normalize('NFKD', texto or '')
        if not unicodedata.combining(caracter)
    )
    limpio = re.sub(r'[^a-zA-Z0-9]+', '_', sin_tildes).strip('_')
    return limpio.lower()


def _listar(documentos):
    """Materializa el queryset y valida que haya algo para imprimir."""
    documentos = list(documentos)
    if not documentos:
        raise ValidationError('No hay documentos para imprimir.')
    return documentos


def _pdf(elementos):
    """Construye un PDF a partir de una lista de flowables y devuelve sus bytes."""
    buffer = io.BytesIO()
    # La misma caja que el resto de los formatos impresos: los márgenes de los
    # que sale `ANCHO_CONTENIDO`, contra el que cada formato calcula sus anchos.
    documento_pdf(buffer).build(elementos, canvasmaker=CanvasNumerado)
    return buffer.getvalue()


def pdf_documento(documento):
    """El PDF de un solo documento, con su formato. Devuelve (contenido, nombre)."""
    return _pdf(_construir(documento)), _nombre_archivo(documento)


def imprimir(documentos):
    """Genera un único PDF con todos los documentos (uno por página). Devuelve (contenido, nombre)."""
    documentos = _listar(documentos)

    elementos = []
    for indice, documento in enumerate(documentos):
        if indice:
            elementos.append(PageBreak())
        elementos.extend(_construir(documento))

    if len(documentos) == 1:
        nombre = _nombre_archivo(documentos[0])
    else:
        nombre = 'documentos.pdf'
    return _pdf(elementos), nombre


def imprimir_zip(documentos):
    """Genera un ZIP con un PDF por documento. Devuelve (contenido, nombre)."""
    documentos = _listar(documentos)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as comprimido:
        for documento in documentos:
            # El id va de sufijo: garantiza nombres únicos dentro del zip aunque
            # dos documentos compartan tipo y número.
            nombre_pdf = _nombre_archivo(documento, sufijo=f'_{documento.id}')
            comprimido.writestr(nombre_pdf, _pdf(_construir(documento)))
    return buffer.getvalue(), 'documentos.zip'
