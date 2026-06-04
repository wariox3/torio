from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumSubtipoCotizante
from humano.serializers import HumSubtipoCotizanteSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


@extend_schema(tags=['Subtipo cotizante'])
class HumSubtipoCotizanteViewSet(viewsets.GenericViewSet):
    serializer_class = HumSubtipoCotizanteSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumSubtipoCotizanteSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumSubtipoCotizante.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumSubtipoCotizanteSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
