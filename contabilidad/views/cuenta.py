from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from contabilidad.models import ConCuenta
from contabilidad.serializers import (
    ConCuentaExportarSerializer,
    ConCuentaImportarSerializer,
    ConCuentaSeleccionarSerializer,
    ConCuentaSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
    OpenApiParameter('exige_base', bool, description='Filtrar por exige base'),
    OpenApiParameter('exige_contacto', bool, description='Filtrar por exige contacto'),
    OpenApiParameter('exige_grupo', bool, description='Filtrar por exige grupo'),
    OpenApiParameter('permite_movimiento', bool, description='Filtrar por permite movimiento'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
]


@extend_schema(tags=['Cuenta'])
class ConCuentaViewSet(
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
    serializer_class = ConCuentaSerializer
    serializer_class_exportar = ConCuentaExportarSerializer
    serializer_class_importar = ConCuentaImportarSerializer

    def get_queryset(self):
        qs = ConCuenta.objects.select_related(
            'cuenta_clase', 'cuenta_grupo', 'cuenta_cuenta', 'cuenta_subcuenta',
        ).order_by('codigo')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)

        for filtro in ('exige_base', 'exige_contacto', 'exige_grupo', 'permite_movimiento'):
            valor = self.request.query_params.get(filtro)
            if valor is not None:
                qs = qs.filter(**{filtro: valor.lower() == 'true'})

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConCuentaSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConCuenta.objects.order_by('codigo')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConCuentaSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
