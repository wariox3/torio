from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumProgramacionDetalle
from humano.serializers import HumProgramacionDetalleSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Programación detalle'])
class HumProgramacionDetalleViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumProgramacionDetalleSerializer

    def get_queryset(self):
        return HumProgramacionDetalle.objects.select_related(
            *HumProgramacionDetalleSerializer.select_related_lista
        )
