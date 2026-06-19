from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from general.models import GenPrecio
from general.serializers import (
    GenPrecioExportarSerializer,
    GenPrecioImportarSerializer,
    GenPrecioSeleccionarSerializer,
    GenPrecioSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('venta', bool, description='Filtrar por precio de venta'),
    OpenApiParameter('compra', bool, description='Filtrar por precio de compra'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Precio'])
class GenPrecioViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenPrecioSerializer
    serializer_class_exportar = GenPrecioExportarSerializer
    serializer_class_importar = GenPrecioImportarSerializer

    def get_queryset(self):
        qs = GenPrecio.objects.order_by('-id')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

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
