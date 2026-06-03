from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from general.models import GenItem
from general.serializers import (
    GenItemExportarSerializer,
    GenItemImportarSerializer,
    GenItemSeleccionarSerializer,
    GenItemSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre, código o referencia'),
    OpenApiParameter('producto', bool, description='Filtrar por producto'),
    OpenApiParameter('servicio', bool, description='Filtrar por servicio'),
    OpenApiParameter('inventario', bool, description='Filtrar por inventario'),
    OpenApiParameter('favorito', bool, description='Filtrar por favorito'),
    OpenApiParameter('inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre, código o referencia'),
]


@extend_schema(tags=['Item'])
class GenItemViewSet(
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
    serializer_class = GenItemSerializer
    serializer_class_exportar = GenItemExportarSerializer
    serializer_class_importar = GenItemImportarSerializer

    def get_queryset(self):
        qs = GenItem.objects.select_related(
            'cuenta_venta', 'cuenta_compra', 'cuenta_costo_venta', 'cuenta_inventario',
        ).order_by('nombre')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(nombre__icontains=search)
                | qs.filter(codigo__icontains=search)
                | qs.filter(referencia__icontains=search)
            )

        for filtro in ('producto', 'servicio', 'inventario', 'favorito', 'inactivo'):
            valor = self.request.query_params.get(filtro)
            if valor is not None:
                qs = qs.filter(**{filtro: valor.lower() == 'true'})

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenItemSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenItem.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(nombre__icontains=search)
                | qs.filter(codigo__icontains=search)
                | qs.filter(referencia__icontains=search)
            )
        pagina = self.paginate_queryset(qs)
        serializer = GenItemSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
