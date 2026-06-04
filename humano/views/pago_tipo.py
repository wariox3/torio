from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumPagoTipo
from humano.serializers import HumPagoTipoSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Pago tipo'])
class HumPagoTipoViewSet(viewsets.GenericViewSet):
    serializer_class = HumPagoTipoSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumPagoTipoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumPagoTipo.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumPagoTipoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
