from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from contabilidad.models import ConMovimiento, ConPeriodo
from contabilidad.serializers import (
    ConMovimientoExportarSerializer,
    ConMovimientoImportarSerializer,
    ConMovimientoSeleccionarSerializer,
    ConMovimientoSerializer,
)
from contabilidad.servicios import inconsistencias_excel
from contabilidad.servicios.movimiento import analizar_inconsistencias
from contabilidad.views.periodo import InconsistenciasResponse
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion
from seguridad.permissions import TienePermisoModelo

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por detalle o cuenta'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por cuenta'),
]

_INCONSISTENCIAS_PARAMS = [
    OpenApiParameter(
        'periodo', int,
        description=(
            'Id del periodo contable (anio*100+mes, por ejemplo 202608). '
            'Sin él se revisa la contabilidad entera.'
        ),
    ),
    OpenApiParameter(
        'excel', bool,
        description='Con `true` devuelve el .xlsx en vez del JSON.',
    ),
]


class ConMovimientoInconsistenciasRequestSerializer(serializers.Serializer):
    # El periodo llega por parámetro y no como pk del detalle: acá el pk es el
    # movimiento. `PrimaryKeyRelatedField` resuelve de una vez el id que no es un
    # número y el periodo que no existe; omitirlo es válido y revisa todo.
    periodo = serializers.PrimaryKeyRelatedField(
        queryset=ConPeriodo.objects.all(), required=False,
    )
    excel = serializers.BooleanField(required=False, default=False)


@extend_schema(tags=['Movimiento'])
class ConMovimientoViewSet(
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
    serializer_class = ConMovimientoSerializer
    serializer_class_exportar = ConMovimientoExportarSerializer
    serializer_class_importar = ConMovimientoImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = ConMovimiento.objects.select_related(
            *ConMovimientoSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(detalle__icontains=search)
                | qs.filter(cuenta__nombre__icontains=search)
                | qs.filter(cuenta__codigo__icontains=search)
            )

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConMovimientoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConMovimiento.objects.select_related('cuenta').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(cuenta__nombre__icontains=search) | qs.filter(cuenta__codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConMovimientoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Consultar las inconsistencias de la contabilidad',
        description=(
            'Devuelve las inconsistencias de los movimientos, sin modificar el estado '
            'de ningún periodo. Con `periodo` se acota a ese periodo; sin él revisa la '
            'contabilidad entera. Es la misma revisión que corre `periodo/bloquear`, '
            'servida desde movimientos para poder consultarla mientras se corrigen los '
            'asientos. Con `excel=true` la misma respuesta se devuelve como archivo.'
        ),
        parameters=_INCONSISTENCIAS_PARAMS,
        responses={
            200: InconsistenciasResponse,
            (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): (
                OpenApiTypes.BINARY
            ),
        },
    )
    @action(detail=False, methods=['get'])
    def inconsistencias(self, request):
        serializer = ConMovimientoInconsistenciasRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        periodo = serializer.validated_data.get('periodo')
        inconsistencias = analizar_inconsistencias(periodo)

        if not serializer.validated_data['excel']:
            return Response({'inconsistencias': inconsistencias})

        contenido, nombre = inconsistencias_excel.excel(inconsistencias)
        response = HttpResponse(
            contenido,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response
