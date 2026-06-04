from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumAdicional
from humano.serializers import (
    HumAdicionalExportarSerializer,
    HumAdicionalImportarSerializer,
    HumAdicionalSeleccionarSerializer,
    HumAdicionalSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
    OpenApiParameter('inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]


@extend_schema(tags=['Adicional'])
class HumAdicionalViewSet(
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
    serializer_class = HumAdicionalSerializer
    serializer_class_exportar = HumAdicionalExportarSerializer
    serializer_class_importar = HumAdicionalImportarSerializer

    def get_queryset(self):
        qs = HumAdicional.objects.select_related(
            *HumAdicionalSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)

        valor = self.request.query_params.get('inactivo')
        if valor is not None:
            qs = qs.filter(inactivo=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumAdicionalSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumAdicional.objects.select_related('contrato__contacto', 'concepto').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumAdicionalSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
