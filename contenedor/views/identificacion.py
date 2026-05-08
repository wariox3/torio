from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnIdentificacion
from contenedor.serializers import CtnIdentificacionSeleccionarSerializer, CtnIdentificacionSerializer

_LIST_PARAMS = [
    OpenApiParameter('pais', str, description='Filtrar por código de país'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('pais', str, description='Filtrar por código de país'),
    OpenApiParameter('search', str, description='Buscar por nombre (retorna 10 resultados)'),
]


@extend_schema(tags=['Identificacion'])
class CtnIdentificacionViewSet(viewsets.ModelViewSet):
    serializer_class = CtnIdentificacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnIdentificacion.objects.select_related('pais').order_by('orden', 'nombre')
        pais = self.request.query_params.get('pais')
        search = self.request.query_params.get('search', '').strip()
        if pais:
            qs = qs.filter(pais_id=pais)
        if search:
            qs = qs.filter(nombre__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=CtnIdentificacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'])
    def seleccionar(self, request):
        qs = CtnIdentificacion.objects.order_by('orden', 'nombre')
        pais = request.query_params.get('pais')
        search = request.query_params.get('search', '').strip()
        if pais:
            qs = qs.filter(pais_id=pais)
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        serializer = CtnIdentificacionSeleccionarSerializer(qs, many=True)
        return Response(serializer.data)
