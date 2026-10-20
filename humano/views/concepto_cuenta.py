from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from humano.models import HumConceptoCuenta
from humano.serializers import HumConceptoCuentaActualizarSerializer, HumConceptoCuentaSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Concepto cuenta'])
class HumConceptoCuentaViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Cuenta contable de cada concepto de nómina por tipo de costo: de aquí la saca
    contabilizar. Un par concepto + tipo de costo tiene una sola cuenta, y al
    editar solo se cambia la cuenta.
    """

    serializer_class = HumConceptoCuentaSerializer

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return HumConceptoCuentaActualizarSerializer
        return HumConceptoCuentaSerializer

    def get_queryset(self):
        return HumConceptoCuenta.objects.select_related(
            *HumConceptoCuentaSerializer.select_related_lista
        )
