from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumLiquidacionAdicional
from humano.serializers import HumLiquidacionAdicionalSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Liquidación adicional'])
class HumLiquidacionAdicionalViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumLiquidacionAdicionalSerializer

    def get_queryset(self):
        return HumLiquidacionAdicional.objects.select_related(
            *HumLiquidacionAdicionalSerializer.select_related_lista
        )
