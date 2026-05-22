from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnEstado
from contenedor.serializers import CtnEstadoSeleccionarSerializer, CtnEstadoSerializer
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('pais', str, description='Filtrar por código de país'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('pais', str, description='Filtrar por código de país'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Estado'])
class CtnEstadoViewSet(viewsets.ModelViewSet):
    serializer_class = CtnEstadoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnEstado.objects.select_related('pais').all()
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

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=CtnEstadoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = CtnEstado.objects.all()
        pais = request.query_params.get('pais')
        search = request.query_params.get('search', '').strip()
        if pais:
            qs = qs.filter(pais_id=pais)
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = CtnEstadoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
