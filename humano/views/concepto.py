from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from humano.models import HumConcepto
from humano.serializers import HumConceptoSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('concepto_tipo_id', int, description='Filtrar por ID de tipo de concepto'),
    OpenApiParameter('adicional', bool, description='Filtrar por adicional'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Concepto'])
class HumConceptoViewSet(viewsets.GenericViewSet):
    serializer_class = HumConceptoSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumConceptoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumConcepto.objects.all()
        concepto_tipo = request.query_params.get('concepto_tipo_id')
        search = request.query_params.get('search', '').strip()
        if concepto_tipo:
            qs = qs.filter(concepto_tipo_id=concepto_tipo)

        valor = request.query_params.get('adicional')
        if valor is not None:
            qs = qs.filter(adicional=valor.lower() == 'true')

        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumConceptoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
