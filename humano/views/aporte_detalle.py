from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumAporteDetalle
from humano.serializers import HumAporteDetalleExportarSerializer, HumAporteDetalleSerializer
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin


@extend_schema(tags=['Aporte detalle'])
class HumAporteDetalleViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumAporteDetalleSerializer
    serializer_class_exportar = HumAporteDetalleExportarSerializer

    def get_queryset(self):
        return HumAporteDetalle.objects.select_related(
            *HumAporteDetalleSerializer.select_related_lista
        )
