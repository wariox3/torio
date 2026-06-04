from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumLiquidacion
from humano.serializers import (
    HumLiquidacionExportarSerializer,
    HumLiquidacionImportarSerializer,
    HumLiquidacionSeleccionarSerializer,
    HumLiquidacionSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
    OpenApiParameter('estado_aprobado', bool, description='Filtrar por aprobado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]


@extend_schema(tags=['Liquidación'])
class HumLiquidacionViewSet(
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
    serializer_class = HumLiquidacionSerializer
    serializer_class_exportar = HumLiquidacionExportarSerializer
    serializer_class_importar = HumLiquidacionImportarSerializer

    def get_queryset(self):
        qs = HumLiquidacion.objects.select_related(
            *HumLiquidacionSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)

        valor = self.request.query_params.get('estado_aprobado')
        if valor is not None:
            qs = qs.filter(estado_aprobado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumLiquidacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumLiquidacion.objects.select_related('contrato__contacto').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumLiquidacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
