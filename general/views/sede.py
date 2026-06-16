from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from general.models import GenSede
from general.serializers import (
    GenSedeExportarSerializer,
    GenSedeImportarSerializer,
    GenSedeSeleccionarSerializer,
    GenSedeSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


@extend_schema(tags=['Sede'])
class GenSedeViewSet(
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
    serializer_class = GenSedeSerializer
    serializer_class_exportar = GenSedeExportarSerializer
    serializer_class_importar = GenSedeImportarSerializer

    def get_queryset(self):
        qs = GenSede.objects.select_related('centro_costo').order_by('nombre')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenSedeSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenSede.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenSedeSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
