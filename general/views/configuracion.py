from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenConfiguracion
from general.serializers import GenConfiguracionSerializer
from utilidades.mixins import SingletonMixin


@extend_schema(tags=['Configuracion'])
class GenConfiguracionViewSet(SingletonMixin, viewsets.GenericViewSet):
    serializer_class = GenConfiguracionSerializer
    modelo_singleton = GenConfiguracion

    @extend_schema(request=GenConfiguracionSerializer, responses=GenConfiguracionSerializer)
    @action(detail=False, methods=['patch'])
    def actualizar(self, request):
        instancia = self._obtener_instancia()
        serializer = GenConfiguracionSerializer(instancia, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
