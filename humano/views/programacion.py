from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumProgramacion
from humano.serializers import (
    HumProgramacionExportarSerializer,
    HumProgramacionImportarSerializer,
    HumProgramacionSeleccionarSerializer,
    HumProgramacionSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
    OpenApiParameter('estado_aprobado', bool, description='Filtrar por aprobado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Programación'])
class HumProgramacionViewSet(
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
    serializer_class = HumProgramacionSerializer
    serializer_class_exportar = HumProgramacionExportarSerializer
    serializer_class_importar = HumProgramacionImportarSerializer

    def get_queryset(self):
        qs = HumProgramacion.objects.select_related(
            *HumProgramacionSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)

        valor = self.request.query_params.get('estado_aprobado')
        if valor is not None:
            qs = qs.filter(estado_aprobado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumProgramacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumProgramacion.objects.order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumProgramacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
