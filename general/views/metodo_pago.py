from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from general.models import GenMetodoPago
from general.serializers import (
    GenMetodoPagoSeleccionarSerializer,
    GenMetodoPagoSerializer,
)
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


@extend_schema(tags=['MetodoPago'])
class GenMetodoPagoViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenMetodoPagoSerializer

    def get_queryset(self):
        return GenMetodoPago.objects.order_by('nombre')

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenMetodoPagoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenMetodoPago.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenMetodoPagoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
