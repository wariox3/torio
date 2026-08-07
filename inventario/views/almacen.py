from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from inventario.models import InvAlmacen
from inventario.serializers import (
    InvAlmacenExportarSerializer,
    InvAlmacenImportarSerializer,
    InvAlmacenSeleccionarSerializer,
    InvAlmacenSerializer,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Almacén'])
class InvAlmacenViewSet(
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
    serializer_class = InvAlmacenSerializer
    serializer_class_exportar = InvAlmacenExportarSerializer
    serializer_class_importar = InvAlmacenImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = InvAlmacen.objects.order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=InvAlmacenSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = InvAlmacen.objects.order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = InvAlmacenSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
