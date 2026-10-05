from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumAporteEntidad
from humano.serializers import HumAporteEntidadExportarSerializer, HumAporteEntidadSerializer
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin


@extend_schema(tags=['Aporte entidad'])
class HumAporteEntidadViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumAporteEntidadSerializer
    serializer_class_exportar = HumAporteEntidadExportarSerializer

    def get_queryset(self):
        return HumAporteEntidad.objects.select_related(
            *HumAporteEntidadSerializer.select_related_lista
        )
