from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumContrato
from humano.serializers import (
    HumContratoExportarSerializer,
    HumContratoImportarSerializer,
    HumContratoSeleccionarSerializer,
    HumContratoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado o identificación'),
    OpenApiParameter('estado_terminado', bool, description='Filtrar por terminado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado o identificación'),
]


@extend_schema(tags=['Contrato'])
class HumContratoViewSet(
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
    serializer_class = HumContratoSerializer
    serializer_class_exportar = HumContratoExportarSerializer
    serializer_class_importar = HumContratoImportarSerializer

    def get_queryset(self):
        qs = HumContrato.objects.select_related(
            *HumContratoSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(contacto__nombre_corto__icontains=search)
                | qs.filter(contacto__numero_identificacion__icontains=search)
            )

        valor = self.request.query_params.get('estado_terminado')
        if valor is not None:
            qs = qs.filter(estado_terminado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumContratoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumContrato.objects.select_related('contacto').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(contacto__nombre_corto__icontains=search)
                | qs.filter(contacto__numero_identificacion__icontains=search)
            )
        pagina = self.paginate_queryset(qs)
        serializer = HumContratoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
