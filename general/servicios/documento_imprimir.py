import io
import re
import unicodedata
import zipfile

from reportlab.platypus import BaseDocTemplate, NextPageTemplate, PageBreak
from rest_framework.exceptions import ValidationError

from general.formatos import (
    FormatoDocumentoCuentaCobro,
    FormatoDocumentoEgreso,
    FormatoDocumentoFactura,
    FormatoDocumentoGenerico,
    FormatoDocumentoNomina,
    FormatoDocumentoPago,
    FormatoDocumentoPos,
    FormatoDocumentoPosElectronico,
    FormatoDocumentoSoporte,
)
from general.models.documento import DOCUMENTO_TIPO_FACTURA_VENTA
from utilidades.formatos.pagina import (
    PAGINA,
    CanvasNumerado,
    MarcaDocumento,
    plantilla_hoja,
    plantilla_rollo,
)

# Qué formato imprime cada tipo de documento. Está quemado a propósito y no sale
# de `GenDocumentoTipo.formato`: mientras sean pocos los tipos con formato propio,
# una columna configurable obliga a sembrarla en cada tenant y a mantenerla en el
# catálogo para que el egreso y el pago salgan bien, y basta que alguien la edite
# para que un comprobante se imprima con el formato equivocado.
#
# El día que sean muchos, esto pasa a ser un mapa por tipo o vuelve a la columna;
# el punto de entrada —`_clase_formato`— no cambia.
DOCUMENTO_TIPO_PAGO = 4  # mismo id que `contabilizar.DOCUMENTO_TIPO_PAGO`
DOCUMENTO_TIPO_EGRESO = 8  # mismo id que `contabilizar.DOCUMENTO_TIPO_EGRESO`
DOCUMENTO_TIPO_DOCUMENTO_SOPORTE = 11
DOCUMENTO_TIPO_CUENTA_COBRO = 17
DOCUMENTO_TIPO_FACTURA_POS_ELECTRONICO = 24
DOCUMENTO_TIPO_FACTURA_POS = 27
# Los de la clase 701: todos se imprimen como desprendible del empleado.
DOCUMENTO_TIPOS_NOMINA = (
    14,  # NOMINA
    20,  # PRIMA
    21,  # CESANTIA
    28,  # LIQUIDACION
    33,  # INTERES CESANTIA
)

FORMATOS = {
    DOCUMENTO_TIPO_FACTURA_VENTA: FormatoDocumentoFactura,
    DOCUMENTO_TIPO_CUENTA_COBRO: FormatoDocumentoCuentaCobro,
    DOCUMENTO_TIPO_FACTURA_POS: FormatoDocumentoPos,
    DOCUMENTO_TIPO_FACTURA_POS_ELECTRONICO: FormatoDocumentoPosElectronico,
    DOCUMENTO_TIPO_DOCUMENTO_SOPORTE: FormatoDocumentoSoporte,
    DOCUMENTO_TIPO_PAGO: FormatoDocumentoPago,
    DOCUMENTO_TIPO_EGRESO: FormatoDocumentoEgreso,
    **{documento_tipo: FormatoDocumentoNomina for documento_tipo in DOCUMENTO_TIPOS_NOMINA},
}


def _clase_formato(documento):
    """La clase de formato del documento. El genérico sirve para cualquiera."""
    return FORMATOS.get(documento.documento_tipo_id, FormatoDocumentoGenerico)


def _construir(documento, identificador):
    """
    Elige la clase de formato según el tipo y devuelve la plantilla de página del
    documento y sus elementos.

    Todos arrancan con su `MarcaDocumento`, numeren o no: es la marca la que le dice
    al canvas dónde termina el documento anterior, así que uno sin numerar que no
    la llevara le sumaría sus páginas al que va antes.

    La plantilla es la hoja estándar o, para un tiquete, el rollo con el alto del
    documento: por eso se arma con los elementos ya construidos.
    """
    clase = _clase_formato(documento)
    elementos = [MarcaDocumento(documento.id, clase.numerar_paginas), *clase(documento).construir()]
    if clase.rollo:
        return plantilla_rollo(identificador, elementos), elementos
    return plantilla_hoja(identificador), elementos


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


def _pdf(documentos):
    """
    Construye un PDF con los documentos, cada uno desde una página nueva, y
    devuelve sus bytes.

    Cada documento trae su plantilla de página, porque no todos van en la misma
    hoja: un lote puede mezclar facturas en hoja carta con tiquetes POS en rollo.
    Al pasar de uno a otro, `NextPageTemplate` cambia la plantilla de la página
    que abre el salto.
    """
    plantillas = []
    elementos = []
    for indice, documento in enumerate(documentos):
        identificador = f'documento_{indice}'
        plantilla, propios = _construir(documento, identificador)
        plantillas.append(plantilla)
        if indice:
            elementos += [NextPageTemplate(identificador), PageBreak()]
        elementos += propios

    buffer = io.BytesIO()
    BaseDocTemplate(buffer, pagesize=PAGINA, pageTemplates=plantillas).build(
        elementos, canvasmaker=CanvasNumerado,
    )
    return buffer.getvalue()


def pdf_documento(documento):
    """El PDF de un solo documento, con su formato. Devuelve (contenido, nombre)."""
    return _pdf([documento]), _nombre_archivo(documento)


def imprimir(documentos):
    """Genera un único PDF con todos los documentos (uno por página). Devuelve (contenido, nombre)."""
    documentos = _listar(documentos)

    if len(documentos) == 1:
        nombre = _nombre_archivo(documentos[0])
    else:
        nombre = 'documentos.pdf'
    return _pdf(documentos), nombre


def imprimir_zip(documentos):
    """Genera un ZIP con un PDF por documento. Devuelve (contenido, nombre)."""
    documentos = _listar(documentos)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as comprimido:
        for documento in documentos:
            # El id va de sufijo: garantiza nombres únicos dentro del zip aunque
            # dos documentos compartan tipo y número.
            nombre_pdf = _nombre_archivo(documento, sufijo=f'_{documento.id}')
            comprimido.writestr(nombre_pdf, _pdf([documento]))
    return buffer.getvalue(), 'documentos.zip'
