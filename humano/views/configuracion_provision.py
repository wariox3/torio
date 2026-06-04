from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumConfiguracionProvision
from humano.serializers import HumConfiguracionProvisionSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por tipo'),
]


@extend_schema(tags=['Configuración provisión'])
class HumConfiguracionProvisionViewSet(viewsets.GenericViewSet):
    serializer_class = HumConfiguracionProvisionSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumConfiguracionProvisionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumConfiguracionProvision.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(tipo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumConfiguracionProvisionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
