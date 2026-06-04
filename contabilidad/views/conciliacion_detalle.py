from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from contabilidad.models import ConConciliacionDetalle
from contabilidad.serializers import ConConciliacionDetalleSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Conciliación detalle'])
class ConConciliacionDetalleViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ConConciliacionDetalleSerializer

    def get_queryset(self):
        return ConConciliacionDetalle.objects.select_related(
            *ConConciliacionDetalleSerializer.select_related_lista
        )
