"""
Detección del tipo real de un archivo a partir de su contenido.

El `content_type` de un upload lo declara el cliente: renombrar un binario a
`.pdf` y anunciarlo como `application/pdf` basta para pasar cualquier chequeo
que se fíe de él. Acá se mira el contenido.

No se usa `python-magic` a propósito: exige libmagic instalado en el sistema y
además devuelve `application/zip` para docx/xlsx según la versión, que es
justo la distinción que hay que hacer. El conjunto de tipos que acepta el
producto es cerrado y chico, así que las firmas se resuelven acá.

Dos familias no se pueden desambiguar por contenido y se tratan como grupo:
OLE2 (`.doc` y `.xls` comparten contenedor) y texto plano (`.txt` y `.csv` no
tienen firma). Para ellas se acepta lo que declare el cliente siempre que caiga
dentro del grupo correcto — que un `.exe` se haga pasar por `.doc` sigue sin
ser posible.
"""

import io
import zipfile

PDF = 'application/pdf'
JPEG = 'image/jpeg'
PNG = 'image/png'
WEBP = 'image/webp'
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
DOC = 'application/msword'
XLS = 'application/vnd.ms-excel'
TXT = 'text/plain'
CSV = 'text/csv'

_FIRMAS = (
    (b'%PDF-', PDF),
    (b'\xff\xd8\xff', JPEG),
    (b'\x89PNG\r\n\x1a\n', PNG),
)

_ZIP = b'PK\x03\x04'
_OLE2 = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def _es_webp(contenido: bytes) -> bool:
    return contenido[:4] == b'RIFF' and contenido[8:12] == b'WEBP'


def _tipo_ooxml(contenido: bytes) -> str | None:
    """docx y xlsx son ZIP: el tipo está en qué carpeta trae adentro."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            nombres = z.namelist()
    except (zipfile.BadZipFile, OSError):
        return None
    if any(n.startswith('word/') for n in nombres):
        return DOCX
    if any(n.startswith('xl/') for n in nombres):
        return XLSX
    return None


def _es_texto(contenido: bytes) -> bool:
    if b'\x00' in contenido[:8192]:
        return False
    try:
        contenido.decode('utf-8')
    except UnicodeDecodeError:
        return False
    return True


def tipos_posibles(contenido: bytes) -> frozenset[str]:
    """
    Tipos compatibles con el contenido. Vacío si no es ninguno conocido.

    Devuelve un conjunto y no un valor único porque OLE2 y el texto plano son
    genuinamente ambiguos.
    """
    for firma, tipo in _FIRMAS:
        if contenido.startswith(firma):
            return frozenset({tipo})
    if _es_webp(contenido):
        return frozenset({WEBP})
    if contenido.startswith(_ZIP):
        tipo = _tipo_ooxml(contenido)
        return frozenset({tipo}) if tipo else frozenset()
    if contenido.startswith(_OLE2):
        return frozenset({DOC, XLS})
    if _es_texto(contenido):
        return frozenset({TXT, CSV})
    return frozenset()
