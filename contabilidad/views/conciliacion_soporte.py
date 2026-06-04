from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from contabilidad.models import ConConciliacionSoporte
from contabilidad.serializers import ConConciliacionSoporteSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Conciliación soporte'])
class ConConciliacionSoporteViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ConConciliacionSoporteSerializer

    def get_queryset(self):
        return ConConciliacionSoporte.objects.select_related(
            *ConConciliacionSoporteSerializer.select_related_lista
        )
