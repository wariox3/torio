from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from contabilidad.models import ConCentroCosto
from contabilidad.serializers import (
    ConCentroCostoExportarSerializer,
    ConCentroCostoImportarSerializer,
    ConCentroCostoSeleccionarSerializer,
    ConCentroCostoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
]


@extend_schema(tags=['Centro de costo'])
class ConCentroCostoViewSet(
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
    serializer_class = ConCentroCostoSerializer
    serializer_class_exportar = ConCentroCostoExportarSerializer
    serializer_class_importar = ConCentroCostoImportarSerializer

    def get_queryset(self):
        qs = ConCentroCosto.objects.order_by('codigo')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConCentroCostoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConCentroCosto.objects.order_by('codigo')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConCentroCostoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
