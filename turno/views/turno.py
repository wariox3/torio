from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from turno.models import TurTurno
from turno.serializers import (
    TurTurnoExportarSerializer,
    TurTurnoImportarSerializer,
    TurTurnoSeleccionarSerializer,
    TurTurnoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
    OpenApiParameter('estado_inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


@extend_schema(tags=['Turno'])
class TurTurnoViewSet(
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
    serializer_class = TurTurnoSerializer
    serializer_class_exportar = TurTurnoExportarSerializer
    serializer_class_importar = TurTurnoImportarSerializer

    def get_queryset(self):
        qs = TurTurno.objects.select_related('novedad_tipo').order_by('nombre')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)

        valor = self.request.query_params.get('estado_inactivo')
        if valor is not None:
            qs = qs.filter(estado_inactivo=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=TurTurnoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = TurTurno.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = TurTurnoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
