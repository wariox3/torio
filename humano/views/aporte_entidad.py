from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumAporteEntidad
from humano.serializers import HumAporteEntidadSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Aporte entidad'])
class HumAporteEntidadViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumAporteEntidadSerializer

    def get_queryset(self):
        return HumAporteEntidad.objects.select_related(
            *HumAporteEntidadSerializer.select_related_lista
        )
