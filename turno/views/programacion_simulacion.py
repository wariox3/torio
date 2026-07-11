from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from general.models import GenDocumentoDetalle
from turno.models import TurProgramacionSimulacion
from turno.serializers import (
    TurProgramacionSimulacionExportarSerializer,
    TurProgramacionSimulacionImportarSerializer,
    TurProgramacionSimulacionSerializer,
)
from turno.servicios import simular as simular_servicio
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin


class SimularRequestSerializer(serializers.Serializer):
    documento_detalle_id = serializers.IntegerField()
    anio = serializers.IntegerField(min_value=2000, max_value=2100)
    mes = serializers.IntegerField(min_value=1, max_value=12)


_LIST_PARAMS = [
    OpenApiParameter('fecha', str, description='Filtrar por fecha (AAAA-MM-DD)'),
    OpenApiParameter('turno', int, description='Filtrar por turno'),
    OpenApiParameter('documento_detalle', int, description='Filtrar por documento detalle'),
]


@extend_schema(tags=['Turno'])
class TurProgramacionSimulacionViewSet(
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
    serializer_class = TurProgramacionSimulacionSerializer
    serializer_class_exportar = TurProgramacionSimulacionExportarSerializer
    serializer_class_importar = TurProgramacionSimulacionImportarSerializer

    def get_queryset(self):
        qs = TurProgramacionSimulacion.objects.select_related(
            *TurProgramacionSimulacionSerializer.select_related_lista
        ).order_by('fecha', 'id')

        fecha = self.request.query_params.get('fecha')
        if fecha:
            qs = qs.filter(fecha=fecha)

        turno = self.request.query_params.get('turno')
        if turno:
            qs = qs.filter(turno_id=turno)

        documento_detalle = self.request.query_params.get('documento_detalle')
        if documento_detalle:
            qs = qs.filter(documento_detalle_id=documento_detalle)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=SimularRequestSerializer)
    @action(detail=False, methods=['post'], url_path='simular')
    def simular(self, request):
        serializer = SimularRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        if not GenDocumentoDetalle.objects.filter(pk=datos['documento_detalle_id']).exists():
            raise NotFound('Documento detalle no encontrado.')

        creados = simular_servicio(
            datos['documento_detalle_id'], datos['anio'], datos['mes'],
        )
        return Response({'creados': creados}, status=status.HTTP_200_OK)
