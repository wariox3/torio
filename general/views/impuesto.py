from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from general.models import GenImpuesto
from general.serializers import GenImpuestoSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o nombre extendido'),
    OpenApiParameter('venta', bool, description='Filtrar impuestos de venta'),
    OpenApiParameter('compra', bool, description='Filtrar impuestos de compra'),
]


@extend_schema(tags=['Impuesto'])
class GenImpuestoViewSet(viewsets.GenericViewSet):
    serializer_class = GenImpuestoSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenImpuestoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenImpuesto.objects.select_related('impuesto_tipo').order_by('id')
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
