from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from general.models import GenAsesor
from general.serializers import (
    GenAsesorExportarSerializer,
    GenAsesorImportarSerializer,
    GenAsesorSeleccionarSerializer,
    GenAsesorSerializer,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre corto'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre corto'),
]


@extend_schema(tags=['Asesor'])
class GenAsesorViewSet(
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
    serializer_class = GenAsesorSerializer
    serializer_class_exportar = GenAsesorExportarSerializer
    serializer_class_importar = GenAsesorImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = GenAsesor.objects.order_by('nombre_corto')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre_corto__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenAsesorSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenAsesor.objects.order_by('nombre_corto')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenAsesorSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
