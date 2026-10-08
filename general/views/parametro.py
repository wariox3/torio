from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from general.models import GenParametro
from general.serializers import GenParametroSerializer
from utilidades.mixins import SingletonMixin


@extend_schema(tags=['Parametro'])
class GenParametroViewSet(SingletonMixin, viewsets.GenericViewSet):
    """
    Solo lectura. A diferencia de `GenConfiguracion`, acá no hay `actualizar`:
    si el front pudiera escribir estos campos, dejarían de ser hechos que produce
    el sistema y pasarían a ser afirmaciones del cliente. Cada uno se escribe por
    el flujo que lo origina (p. ej. `gen_asistente_electronico_venta` y `_nomina` por
    `electronico/asistente-terminar/`).
    """

    serializer_class = GenParametroSerializer
    modelo_singleton = GenParametro
