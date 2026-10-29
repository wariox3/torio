from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ParseError, UnsupportedMediaType, ValidationError

from contabilidad.models import ConMovimiento
from contabilidad.serializers import (
    ConMovimientoInformeExportarSerializer,
    ConMovimientoInformeSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin

# Registro de informes planos sobre ConMovimiento, con el mismo estándar que los
# de GenDocumento: cada informe declara su invariante (`filtro`, garantizada por
# el servidor) y las columnas las aporta el serializer estándar, salvo que el
# informe traiga `serializer` / `exportar` propios. `titulo` va encima de la
# tabla en el Excel (`ExportarExcelMixin`).
#
# Los informes agregados de contabilidad (balances, auxiliares, estados) siguen en
# `ConMovimientoInformePersonalizadoViewSet`: tienen jerarquía y su propio Excel.
INFORMES = {
    # Todos los movimientos; el rango y lo demás van como filtros dinámicos.
    'movimiento': {
        'titulo': 'Movimientos',
        'filtro': Q(),
    },
}


@extend_schema(tags=['Informe: Movimiento'])
class ConMovimientoInformeViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    viewsets.GenericViewSet,
):
    """
    Punto único de informes planos sobre ConMovimiento: un renglón por movimiento.

    El informe se elige con el parámetro `informe` (body o query string).

        POST /lista/    { "informe": "...", "filtros": [...], "ordenamientos": [...] }
        POST /excel/    { "informe": "...", "filtros": [...], "ordenamientos": [...] }
    """

    def _informe(self):
        # Generación de esquema (drf-spectacular): no hay request real, no filtrar.
        if getattr(self, 'swagger_fake_view', False):
            return {'filtro': Q()}

        request = getattr(self, 'request', None)
        clave = None
        if request is not None:
            try:
                clave = request.data.get('informe')
            except (ParseError, UnsupportedMediaType, AttributeError):  # body mal formado o que no es un objeto
                clave = None
            if not clave:
                clave = request.query_params.get('informe')
        if not clave:
            raise ValidationError({'detail': 'El campo informe es requerido.'})
        if clave not in INFORMES:
            raise ValidationError(
                {'detail': f'Informe "{clave}" no existe. Opciones: {", ".join(sorted(INFORMES))}.'}
            )
        return INFORMES[clave]

    def get_serializer_class(self):
        return self._informe().get('serializer', ConMovimientoInformeSerializer)

    def get_titulo_excel(self, serializer):
        return self._informe().get('titulo')

    def get_serializer_exportar(self):
        return self._informe().get('exportar', ConMovimientoInformeExportarSerializer)()

    def get_queryset(self):
        return ConMovimiento.objects.filter(self._informe()['filtro'])
