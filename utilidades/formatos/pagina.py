"""
La geometría común de los formatos impresos: tamaño, márgenes y ancho útil.

Existe porque el ancho no es una decisión de cada formato. Cuando cada uno elegía
los suyos, el certificado de retención terminó con una tabla de 17,40 cm dentro
de un marco de 17,19 cm —dos milímetros de más, invisibles hasta que algo se
desborda— y el encabezado tomaba su ancho de esa misma suma equivocada.

Con `ANCHO_CONTENIDO` los anchos de columna se declaran como fracciones de lo que
realmente hay, y `documento_pdf` garantiza que el marco que las recibe sea el
mismo que se usó para calcularlas.
"""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate

PAGINA = letter
MARGEN_HORIZONTAL = 1.1 * cm
MARGEN_VERTICAL = 2 * cm

# Lo que queda para el contenido. Es el ancho contra el que se calcula cualquier
# tabla o bloque a lo ancho de la hoja.
ANCHO_CONTENIDO = PAGINA[0] - 2 * MARGEN_HORIZONTAL


def anchos(*fracciones):
    """
    Reparte `ANCHO_CONTENIDO` entre columnas dadas como fracciones.

        anchos(0.55, 0.225, 0.225)

    El sobrante del redondeo va a la última columna, para que la suma dé exacta
    y la tabla no quede ni corta ni desbordada por unas milésimas.
    """
    if not fracciones:
        raise ValueError('Se necesita al menos una fracción.')
    medidas = [ANCHO_CONTENIDO * fraccion for fraccion in fracciones[:-1]]
    medidas.append(ANCHO_CONTENIDO - sum(medidas))
    return medidas


def documento_pdf(buffer, titulo=None):
    """El `SimpleDocTemplate` estándar, con los márgenes de los que sale `ANCHO_CONTENIDO`."""
    return SimpleDocTemplate(
        buffer,
        pagesize=PAGINA,
        leftMargin=MARGEN_HORIZONTAL,
        rightMargin=MARGEN_HORIZONTAL,
        topMargin=MARGEN_VERTICAL,
        bottomMargin=MARGEN_VERTICAL,
        title=titulo or '',
    )
