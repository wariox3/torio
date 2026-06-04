from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumConfiguracionAporte
from humano.serializers import HumConfiguracionAporteSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por tipo'),
]


@extend_schema(tags=['Configuración aporte'])
class HumConfiguracionAporteViewSet(viewsets.GenericViewSet):
    serializer_class = HumConfiguracionAporteSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumConfiguracionAporteSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumConfiguracionAporte.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(tipo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumConfiguracionAporteSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
