from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from turno.models import TurProgramacion
from turno.serializers import (
    TurProgramacionExportarSerializer,
    TurProgramacionImportarSerializer,
    TurProgramacionSeleccionarSerializer,
    TurProgramacionSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('contrato', int, description='Filtrar por contrato'),
    OpenApiParameter('fecha', str, description='Filtrar por fecha (AAAA-MM-DD)'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('contrato', int, description='Filtrar por contrato'),
]


@extend_schema(tags=['Turno'])
class TurProgramacionViewSet(
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
    serializer_class = TurProgramacionSerializer
    serializer_class_exportar = TurProgramacionExportarSerializer
    serializer_class_importar = TurProgramacionImportarSerializer

    def get_queryset(self):
        qs = TurProgramacion.objects.select_related(
            *TurProgramacionSerializer.select_related_lista
        ).order_by('fecha', 'id')

        contrato = self.request.query_params.get('contrato')
        if contrato:
            qs = qs.filter(contrato_id=contrato)

        fecha = self.request.query_params.get('fecha')
        if fecha:
            qs = qs.filter(fecha=fecha)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=TurProgramacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = TurProgramacion.objects.select_related(
            'contrato__contacto', 'turno'
        ).order_by('fecha', 'id')
        contrato = request.query_params.get('contrato')
        if contrato:
            qs = qs.filter(contrato_id=contrato)
        pagina = self.paginate_queryset(qs)
        serializer = TurProgramacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
