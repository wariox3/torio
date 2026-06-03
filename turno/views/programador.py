from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from turno.models import TurProgramador
from turno.serializers import (
    TurProgramadorExportarSerializer,
    TurProgramadorImportarSerializer,
    TurProgramadorSeleccionarSerializer,
    TurProgramadorSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
    OpenApiParameter('estado_inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Programador'])
class TurProgramadorViewSet(
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
    serializer_class = TurProgramadorSerializer
    serializer_class_exportar = TurProgramadorExportarSerializer
    serializer_class_importar = TurProgramadorImportarSerializer

    def get_queryset(self):
        qs = TurProgramador.objects.order_by('nombre')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)

        valor = self.request.query_params.get('estado_inactivo')
        if valor is not None:
            qs = qs.filter(estado_inactivo=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=TurProgramadorSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = TurProgramador.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = TurProgramadorSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
