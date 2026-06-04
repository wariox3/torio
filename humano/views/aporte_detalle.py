from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumAporteDetalle
from humano.serializers import HumAporteDetalleSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Aporte detalle'])
class HumAporteDetalleViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumAporteDetalleSerializer

    def get_queryset(self):
        return HumAporteDetalle.objects.select_related(
            *HumAporteDetalleSerializer.select_related_lista
        )
