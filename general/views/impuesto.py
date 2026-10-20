from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenImpuesto
from general.serializers import (
    GenImpuestoActualizarSerializer,
    GenImpuestoSeleccionarSerializer,
    GenImpuestoSerializer,
)
from utilidades.mixins import FiltrosDinamicosMixin
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o nombre extendido'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o nombre extendido'),
    OpenApiParameter('venta', bool, description='Filtrar impuestos de venta'),
    OpenApiParameter('compra', bool, description='Filtrar impuestos de compra'),
]


@extend_schema(tags=['Impuesto'])
class GenImpuestoViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Catálogo normativo: los impuestos los siembra `general/catalogos/19_impuesto.json`
    y no se crean ni se borran por la API. Lo único que cada tenant configura es la
    cuenta contable, y eso es lo único que acepta el PATCH.
    """

    serializer_class = GenImpuestoSerializer

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return GenImpuestoActualizarSerializer
        return GenImpuestoSerializer

    def get_queryset(self):
        qs = GenImpuesto.objects.select_related(*GenImpuestoSerializer.select_related_lista)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(nombre_extendido__icontains=search)
        return qs

    @extend_schema(responses=GenImpuestoSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=None)
    def configuracion(self, request):
        """Todos los impuestos, sin paginar ni filtrar: la pantalla de configuración los muestra completos."""
        qs = GenImpuesto.objects.select_related(*GenImpuestoSerializer.select_related_lista).order_by('id')
        return Response(GenImpuestoSerializer(qs, many=True).data)

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenImpuestoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenImpuesto.objects.select_related('impuesto_tipo', 'cuenta').order_by('id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(nombre_extendido__icontains=search)
        if request.query_params.get('venta') in ('true', 'True', '1'):
            qs = qs.filter(venta=True)
        if request.query_params.get('compra') in ('true', 'True', '1'):
            qs = qs.filter(compra=True)
        pagina = self.paginate_queryset(qs)
        serializer = GenImpuestoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
