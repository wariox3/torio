from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumTipoCosto
from humano.serializers import HumTipoCostoSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Tipo costo'])
class HumTipoCostoViewSet(viewsets.GenericViewSet):
    serializer_class = HumTipoCostoSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumTipoCostoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumTipoCosto.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumTipoCostoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
