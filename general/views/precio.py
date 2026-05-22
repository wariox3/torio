from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from general.models import GenPrecio
from general.serializers import GenPrecioSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('venta', bool, description='Filtrar por precio de venta'),
    OpenApiParameter('compra', bool, description='Filtrar por precio de compra'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Precio'])
class GenPrecioViewSet(viewsets.GenericViewSet):
    serializer_class = GenPrecioSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenPrecioSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenPrecio.objects.all()
        search = request.query_params.get('search', '').strip()
        for filtro in ('venta', 'compra'):
            valor = request.query_params.get(filtro)
            if valor is not None:
                qs = qs.filter(**{filtro: valor.lower() == 'true'})
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenPrecioSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
