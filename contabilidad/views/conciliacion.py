from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from contabilidad.models import ConConciliacion
from contabilidad.serializers import (
    ConConciliacionExportarSerializer,
    ConConciliacionImportarSerializer,
    ConConciliacionSeleccionarSerializer,
    ConConciliacionSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por cuenta banco'),
]


@extend_schema(tags=['Conciliación'])
class ConConciliacionViewSet(
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
    serializer_class = ConConciliacionSerializer
    serializer_class_exportar = ConConciliacionExportarSerializer
    serializer_class_importar = ConConciliacionImportarSerializer

    def get_queryset(self):
        return ConConciliacion.objects.select_related(
            *ConConciliacionSerializer.select_related_lista
        ).order_by('-id')

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConConciliacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConConciliacion.objects.select_related('cuenta_banco').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(cuenta_banco__nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConConciliacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
