from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumEntidad
from humano.serializers import HumEntidadSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


@extend_schema(tags=['Entidad'])
class HumEntidadViewSet(viewsets.GenericViewSet):
    serializer_class = HumEntidadSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumEntidadSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumEntidad.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumEntidadSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
