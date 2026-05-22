from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from general.models import GenCiudad
from general.serializers import GenCiudadSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('estado', int, description='Filtrar por ID de estado'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Ciudad'])
class GenCiudadViewSet(viewsets.GenericViewSet):
    serializer_class = GenCiudadSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenCiudadSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenCiudad.objects.all()
        estado = request.query_params.get('estado')
        search = request.query_params.get('search', '').strip()
        if estado:
            qs = qs.filter(estado_id=estado)
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenCiudadSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
