from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumNovedad
from humano.serializers import (
    HumNovedadExportarSerializer,
    HumNovedadImportarSerializer,
    HumNovedadSeleccionarSerializer,
    HumNovedadSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]


@extend_schema(tags=['Novedad'])
class HumNovedadViewSet(
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
    serializer_class = HumNovedadSerializer
    serializer_class_exportar = HumNovedadExportarSerializer
    serializer_class_importar = HumNovedadImportarSerializer

    def get_queryset(self):
        qs = HumNovedad.objects.select_related(
            *HumNovedadSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumNovedadSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumNovedad.objects.select_related('contrato__contacto', 'novedad_tipo').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumNovedadSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
