from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumAporte
from humano.serializers import (
    HumAporteExportarSerializer,
    HumAporteImportarSerializer,
    HumAporteSeleccionarSerializer,
    HumAporteSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('estado_aprobado', bool, description='Filtrar por aprobado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por año'),
]


@extend_schema(tags=['Aporte'])
class HumAporteViewSet(
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
    serializer_class = HumAporteSerializer
    serializer_class_exportar = HumAporteExportarSerializer
    serializer_class_importar = HumAporteImportarSerializer

    def get_queryset(self):
        qs = HumAporte.objects.select_related(
            *HumAporteSerializer.select_related_lista
        ).order_by('-id')

        valor = self.request.query_params.get('estado_aprobado')
        if valor is not None:
            qs = qs.filter(estado_aprobado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumAporteSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumAporte.objects.order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(anio__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumAporteSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
