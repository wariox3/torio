import io
import zipfile

from reportlab.lib.pagesizes import letter
from reportlab.platypus import PageBreak, SimpleDocTemplate
from rest_framework.exceptions import ValidationError

from general.servicios.formatos import FormatoGenerico

# Registro de formatos por su valor en GenDocumentoTipo.formato. Para sumar uno nuevo:
# 1) agregar el valor a GenDocumentoTipo.FORMATO_CHOICES, 2) crear su clase en formatos/,
# 3) registrarla aquí.
FORMATOS = {
    'generico': FormatoGenerico,
}


def _construir(documento):
    """Elige la clase de formato según el tipo y devuelve los elementos del documento."""
    formato = documento.documento_tipo.formato
    clase = FORMATOS.get(formato)
    if clase is None:
        raise ValidationError(f'No hay un formato de impresión configurado para «{formato}».')
    return clase(documento).construir()


def _listar(documentos):
    """Materializa el queryset y valida que haya algo para imprimir."""
    documentos = list(documentos)
    if not documentos:
        raise ValidationError('No hay documentos para imprimir.')
    return documentos


def _pdf(elementos):
    """Construye un PDF a partir de una lista de flowables y devuelve sus bytes."""
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=letter).build(elementos)
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
        unico = documentos[0]
        nombre = f'{unico.documento_tipo.nombre}-{unico.numero or unico.id}.pdf'
    else:
        nombre = 'documentos.pdf'
    return _pdf(elementos), nombre


def imprimir_zip(documentos):
    """Genera un ZIP con un PDF por documento. Devuelve (contenido, nombre)."""
    documentos = _listar(documentos)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as comprimido:
        for documento in documentos:
            # El id garantiza nombres únicos aunque coincidan tipo y número.
            nombre_pdf = f'{documento.documento_tipo.nombre}-{documento.numero or "SN"}-{documento.id}.pdf'
            comprimido.writestr(nombre_pdf, _pdf(_construir(documento)))
    return buffer.getvalue(), 'documentos.zip'
