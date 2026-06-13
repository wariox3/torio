from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets

from turno.models import TurSoporte
from turno.serializers import (
    TurSoporteExportarSerializer,
    TurSoporteImportarSerializer,
    TurSoporteSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin

_LIST_PARAMS = [
    OpenApiParameter('grupo', int, description='Filtrar por grupo'),
    OpenApiParameter('fecha_desde', str, description='Filtrar por fecha desde (AAAA-MM-DD)'),
    OpenApiParameter('fecha_hasta', str, description='Filtrar por fecha hasta (AAAA-MM-DD)'),
]


@extend_schema(tags=['Turno'])
class TurSoporteViewSet(
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
    serializer_class = TurSoporteSerializer
    serializer_class_exportar = TurSoporteExportarSerializer
    serializer_class_importar = TurSoporteImportarSerializer

    def get_queryset(self):
        qs = TurSoporte.objects.select_related(
            *TurSoporteSerializer.select_related_lista
        ).order_by('fecha_desde', 'id')

        grupo = self.request.query_params.get('grupo')
        if grupo:
            qs = qs.filter(grupo_id=grupo)

        fecha_desde = self.request.query_params.get('fecha_desde')
        if fecha_desde:
            qs = qs.filter(fecha_desde=fecha_desde)

        fecha_hasta = self.request.query_params.get('fecha_hasta')
        if fecha_hasta:
            qs = qs.filter(fecha_hasta=fecha_hasta)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
