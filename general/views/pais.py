from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from general.models import GenPais
from general.serializers import GenPaisSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
]


@extend_schema(tags=['País'])
class GenPaisViewSet(viewsets.GenericViewSet):
    serializer_class = GenPaisSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenPaisSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenPais.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenPaisSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
