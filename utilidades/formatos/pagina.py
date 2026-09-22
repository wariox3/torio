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
from collections import Counter

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, SimpleDocTemplate

PAGINA = letter
MARGEN_HORIZONTAL = 1.1 * cm
# Arriba y abajo no son simétricos: el encabezado ya trae su propio aire —la
# marca de origen y la barra del título— y un margen alto lo empujaba media hoja
# hacia abajo. Abajo se conserva, que es donde caen las firmas.
MARGEN_SUPERIOR = 1 * cm
MARGEN_INFERIOR = 2 * cm

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
        topMargin=MARGEN_SUPERIOR,
        bottomMargin=MARGEN_INFERIOR,
        title=titulo or '',
    )


# --- Número de página ------------------------------------------------------
#
# «Página X de Y» cuenta por documento, no por archivo: `documento_imprimir` junta
# varios documentos en un solo PDF, y la tercera hoja del archivo puede ser la
# primera de la segunda factura. Y solo se numera lo que lo pide: en un lote que
# mezcla facturas con pagos, el pago no lleva número ni le suma páginas a la
# factura que va antes.
#
# Cada documento empieza con una `MarcaDocumento`, que al dibujarse le dice al
# canvas qué documento empieza. El canvas guarda las páginas en vez de emitirlas,
# y al final —cuando ya sabe cuántas tiene cada documento— les pone el número.

COLOR_NUMERO_PAGINA = colors.HexColor('#595959')


class MarcaDocumento(Flowable):
    """
    Marca invisible del comienzo de un documento dentro del PDF.

    No ocupa espacio. Va primera en los flowables del documento, así que se dibuja
    en su primera página y todas las páginas hasta la siguiente marca son suyas.
    """

    def __init__(self, clave, numerar):
        super().__init__()
        self.clave = clave
        self.numerar = numerar
        self.width = self.height = 0

    def wrap(self, ancho_disponible, alto_disponible):
        return 0, 0

    def draw(self):
        marcar = getattr(self.canv, 'marcar_documento', None)
        if marcar is not None:
            marcar(self.clave, self.numerar)


class CanvasNumerado(canvas.Canvas):
    """Canvas que pone «Página X de Y» a las páginas de los documentos que lo piden."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self._documento = None

    def marcar_documento(self, clave, numerar):
        self._documento = (clave, numerar)

    def showPage(self):
        # Se guarda el estado de la página en vez de emitirla: todavía no se sabe
        # cuántas va a tener el documento.
        self._paginas.append((dict(self.__dict__), self._documento))
        self._startPage()

    def save(self):
        totales = Counter(documento for _, documento in self._paginas)
        vistas = Counter()
        for estado, documento in self._paginas:
            self.__dict__.update(estado)
            vistas[documento] += 1
            if documento is not None and documento[1]:
                self.numero_pagina(vistas[documento], totales[documento])
            super().showPage()
        super().save()

    def numero_pagina(self, pagina, total):
        """Abajo a la derecha, dentro del margen inferior, donde no pisa las firmas."""
        self.saveState()
        self.setFont('Helvetica-Bold', 7.5)
        self.setFillColor(COLOR_NUMERO_PAGINA)
        self.drawRightString(
            PAGINA[0] - MARGEN_HORIZONTAL, MARGEN_INFERIOR / 2, f'Página {pagina} de {total}',
        )
        self.restoreState()
