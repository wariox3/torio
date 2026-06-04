from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumConceptoCuenta
from humano.serializers import HumConceptoCuentaSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Concepto cuenta'])
class HumConceptoCuentaViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumConceptoCuentaSerializer

    def get_queryset(self):
        return HumConceptoCuenta.objects.select_related(
            *HumConceptoCuentaSerializer.select_related_lista
        )
