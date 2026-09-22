class FormatoBase:
    """Base de los formatos de impresión: recibe un documento y devuelve sus flowables."""

    # Si sus páginas llevan «Página X de Y» (ver `utilidades.formatos.pagina`).
    numerar_paginas = False

    def __init__(self, documento):
        self.documento = documento

    def construir(self):
        """Devuelve la lista de flowables (elementos reportlab) del documento."""
        raise NotImplementedError
