from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from general.models import GenCuentaBanco
from general.serializers import (
    GenCuentaBancoExportarSerializer,
    GenCuentaBancoImportarSerializer,
    GenCuentaBancoSeleccionarSerializer,
    GenCuentaBancoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o número de cuenta'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o número de cuenta'),
]


@extend_schema(tags=['Cuenta bancaria'])
class GenCuentaBancoViewSet(
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
    serializer_class = GenCuentaBancoSerializer
    serializer_class_exportar = GenCuentaBancoExportarSerializer
    serializer_class_importar = GenCuentaBancoImportarSerializer

    def get_queryset(self):
        qs = GenCuentaBanco.objects.select_related(
            'cuenta_banco_tipo', 'cuenta_banco_clase', 'cuenta',
        ).order_by('nombre')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(numero_cuenta__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenCuentaBancoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenCuentaBanco.objects.order_by('nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(numero_cuenta__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenCuentaBancoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
