from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets

from turno.models import TurPrototipo
from turno.serializers import (
    TurPrototipoExportarSerializer,
    TurPrototipoImportarSerializer,
    TurPrototipoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin

_LIST_PARAMS = [
    OpenApiParameter('documento_detalle', int, description='Filtrar por documento detalle'),
    OpenApiParameter('secuencia', int, description='Filtrar por secuencia'),
    OpenApiParameter('fecha_inicio', str, description='Filtrar por fecha inicio (AAAA-MM-DD)'),
]


@extend_schema(tags=['Turno'])
class TurPrototipoViewSet(
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
    serializer_class = TurPrototipoSerializer
    serializer_class_exportar = TurPrototipoExportarSerializer
    serializer_class_importar = TurPrototipoImportarSerializer

    def get_queryset(self):
        qs = TurPrototipo.objects.select_related(
            *TurPrototipoSerializer.select_related_lista
        ).order_by('fecha', 'id')

        documento_detalle = self.request.query_params.get('documento_detalle')
        if documento_detalle:
            qs = qs.filter(documento_detalle_id=documento_detalle)

        secuencia = self.request.query_params.get('secuencia')
        if secuencia:
            qs = qs.filter(secuencia_id=secuencia)

        fecha_inicio = self.request.query_params.get('fecha_inicio')
        if fecha_inicio:
            qs = qs.filter(fecha_inicio=fecha_inicio)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
