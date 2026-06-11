from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from general.models import GenDocumentoDetalle
from general.serializers import (
    GenDocumentoDetalleInformeExportarSerializer,
    GenDocumentoDetalleInformeSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin

# Registro de informes sobre GenDocumentoDetalle.
# Cada informe declara su invariante (`filtro`, garantizada por el servidor). Las
# columnas las aporta el serializer estándar; un informe puede sobreescribirlas
# con `serializer` / `exportar` si lo necesita.
INFORMES = {
    'pendiente_facturar': {
        'filtro': Q(pendiente__gt=0),
    },
}

_INFORME_DEFAULT = 'pendiente_facturar'


@extend_schema(tags=['Informe: Documento detalle'])
class GenDocumentoDetalleInformeViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    viewsets.GenericViewSet,
):
    """
    Punto único de informes sobre GenDocumentoDetalle.

    El informe se elige con el parámetro `informe` (body o query string). Cada
    informe define en `INFORMES` su invariante (filtro garantizado por el
    servidor) y, opcionalmente, su serializer de columnas.

        POST /lista/    { "informe": "...", "filtros": [...] }
        POST /excel/    { "informe": "...", "filtros": [...] }
    """

    def _informe(self):
        # Generación de esquema (drf-spectacular): no hay request real, usar default.
        if getattr(self, 'swagger_fake_view', False):
            return INFORMES[_INFORME_DEFAULT]

        request = getattr(self, 'request', None)
        clave = None
        if request is not None:
            try:
                clave = request.data.get('informe')
            except Exception:
                clave = None
            if not clave:
                clave = request.query_params.get('informe')
        if not clave:
            raise ValidationError({'informe': 'Este campo es requerido.'})
        if clave not in INFORMES:
            raise ValidationError(
                {'informe': f'Informe "{clave}" no existe. Opciones: {sorted(INFORMES)}.'}
            )
        return INFORMES[clave]

    def get_serializer_class(self):
        return self._informe().get('serializer', GenDocumentoDetalleInformeSerializer)

    def get_serializer_exportar(self):
        return self._informe().get('exportar', GenDocumentoDetalleInformeExportarSerializer)()

    def get_queryset(self):
        return GenDocumentoDetalle.objects.filter(self._informe()['filtro'])
