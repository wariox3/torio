from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from turno.models import TurPuesto
from turno.serializers import (
    TurPuestoExportarSerializer,
    TurPuestoImportarSerializer,
    TurPuestoSeleccionarSerializer,
    TurPuestoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o dirección'),
    OpenApiParameter('estado_inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Puesto'])
class TurPuestoViewSet(
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
    serializer_class = TurPuestoSerializer
    serializer_class_exportar = TurPuestoExportarSerializer
    serializer_class_importar = TurPuestoImportarSerializer

    def get_queryset(self):
        qs = TurPuesto.objects.select_related(
            'contacto', 'programador', 'ciudad', 'centro_costo',
        ).order_by('nombre')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(direccion__icontains=search)

        valor = self.request.query_params.get('estado_inactivo')
        if valor is not None:
            qs = qs.filter(estado_inactivo=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=TurPuestoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = TurPuesto.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = TurPuestoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
