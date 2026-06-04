from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumPension
from humano.serializers import HumPensionSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Pensión'])
class HumPensionViewSet(viewsets.GenericViewSet):
    serializer_class = HumPensionSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumPensionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumPension.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumPensionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
