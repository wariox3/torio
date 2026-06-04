from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from contabilidad.models import ConMovimiento
from contabilidad.serializers import (
    ConMovimientoExportarSerializer,
    ConMovimientoImportarSerializer,
    ConMovimientoSeleccionarSerializer,
    ConMovimientoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por detalle o cuenta'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por cuenta'),
]


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
