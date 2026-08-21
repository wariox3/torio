from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from general.models import GenParametro
from general.serializers import GenParametroSerializer
from utilidades.mixins import SingletonMixin


@extend_schema(tags=['Parametro'])
class GenParametroViewSet(SingletonMixin, viewsets.GenericViewSet):
    """
    Solo lectura. A diferencia de `GenConfiguracion`, acá no hay `actualizar`:
    si el front pudiera escribir estos campos, `gen_factura_electronica_activa`
    dejaría de ser un hecho verificado contra el servicio de facturación
    electrónica y pasaría a ser una afirmación del cliente.
    """

    serializer_class = GenParametroSerializer
    modelo_singleton = GenParametro
