from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnCiudad
from contenedor.serializers import CtnCiudadSeleccionarSerializer, CtnCiudadSerializer

_LIST_PARAMS = [
    OpenApiParameter('estado', int, description='Filtrar por ID de estado'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('estado', int, description='Filtrar por ID de estado'),
    OpenApiParameter('search', str, description='Buscar por nombre (retorna 10 resultados)'),
]


@extend_schema(tags=['Ciudad'])
class CtnCiudadViewSet(viewsets.ModelViewSet):
    serializer_class = CtnCiudadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnCiudad.objects.select_related('estado').all()
        estado = self.request.query_params.get('estado')
        search = self.request.query_params.get('search', '').strip()
        if estado:
            qs = qs.filter(estado_id=estado)
        if search:
            qs = qs.filter(nombre__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=CtnCiudadSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'])
    def seleccionar(self, request):
        qs = CtnCiudad.objects.all()
        estado = request.query_params.get('estado')
        search = request.query_params.get('search', '').strip()
        if estado:
            qs = qs.filter(estado_id=estado)
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        serializer = CtnCiudadSeleccionarSerializer(qs, many=True)
        return Response(serializer.data)
