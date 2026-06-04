from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumAporteContrato
from humano.serializers import HumAporteContratoSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Aporte contrato'])
class HumAporteContratoViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumAporteContratoSerializer

    def get_queryset(self):
        return HumAporteContrato.objects.select_related(
            *HumAporteContratoSerializer.select_related_lista
        )
