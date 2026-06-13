from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from turno.models import TurSoporteDetalle
from turno.serializers import TurSoporteDetalleSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Soporte detalle'])
class TurSoporteDetalleViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = TurSoporteDetalleSerializer

    def get_queryset(self):
        return TurSoporteDetalle.objects.select_related(
            *TurSoporteDetalleSerializer.select_related_lista
        )
