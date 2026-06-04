from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from contabilidad.models import ConPeriodo
from contabilidad.serializers import (
    ConPeriodoExportarSerializer,
    ConPeriodoImportarSerializer,
    ConPeriodoSeleccionarSerializer,
    ConPeriodoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('anio', int, description='Filtrar por año'),
    OpenApiParameter('estado_cerrado', bool, description='Filtrar por cerrado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por año'),
]


@extend_schema(tags=['Periodo'])
class ConPeriodoViewSet(
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
    serializer_class = ConPeriodoSerializer
    serializer_class_exportar = ConPeriodoExportarSerializer
    serializer_class_importar = ConPeriodoImportarSerializer

    def get_queryset(self):
        qs = ConPeriodo.objects.order_by('-anio', '-mes')

        anio = self.request.query_params.get('anio')
        if anio:
            qs = qs.filter(anio=anio)

        valor = self.request.query_params.get('estado_cerrado')
        if valor is not None:
            qs = qs.filter(estado_cerrado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConPeriodoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConPeriodo.objects.order_by('-anio', '-mes')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(anio__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConPeriodoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
