class FormatoBase:
    """Base de los formatos de impresión: recibe un documento y devuelve sus flowables."""

    def __init__(self, documento):
        self.documento = documento

    def construir(self):
        """Devuelve la lista de flowables (elementos reportlab) del documento."""
        raise NotImplementedError
