"""
Paginación reutilizable para ViewSets de DRF.
"""
from rest_framework.pagination import PageNumberPagination


class SeleccionarPaginacion(PageNumberPagination):
    """Paginación estándar para las acciones `seleccionar/` (10 por página)."""

    page_size = 10
