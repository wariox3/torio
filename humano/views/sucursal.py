from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumSucursal
from humano.serializers import (
    HumSucursalExportarSerializer,
    HumSucursalImportarSerializer,
    HumSucursalSeleccionarSerializer,
    HumSucursalSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


@extend_schema(tags=['Sucursal'])
class HumSucursalViewSet(
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
    serializer_class = HumSucursalSerializer
    serializer_class_exportar = HumSucursalExportarSerializer
    serializer_class_importar = HumSucursalImportarSerializer

    def get_queryset(self):
        qs = HumSucursal.objects.order_by('nombre')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumSucursalSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumSucursal.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumSucursalSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
