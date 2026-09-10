import io
import re
import unicodedata
import zipfile

from reportlab.platypus import PageBreak
from rest_framework.exceptions import ValidationError

from general.formatos import FormatoDocumentoGenerico
from utilidades.formatos.pagina import documento_pdf

# Registro de formatos por su valor en GenDocumentoTipo.formato. Para sumar uno nuevo:
# 1) agregar el valor a GenDocumentoTipo.FORMATO_CHOICES, 2) crear su clase en formatos/,
# 3) registrarla aquí.
FORMATOS = {
    'generico': FormatoDocumentoGenerico,
}


def _construir(documento):
    """Elige la clase de formato según el tipo y devuelve los elementos del documento."""
    formato = documento.documento_tipo.formato
    clase = FORMATOS.get(formato)
    if clase is None:
        raise ValidationError(f'No hay un formato de impresión configurado para «{formato}».')
    return clase(documento).construir()


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
    documento_pdf(buffer).build(elementos)
    return buffer.getvalue()


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
