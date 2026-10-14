from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenDocumentoConceptoCorreccion
from general.serializers import GenDocumentoConceptoCorreccionSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
    OpenApiParameter(
        'documento_clase_id', int,
        description='Solo los conceptos de esa clase de nota (101 nota crédito de venta)',
    ),
]


@extend_schema(tags=['DocumentoConceptoCorreccion'])
class GenDocumentoConceptoCorreccionViewSet(viewsets.GenericViewSet):
    serializer_class = GenDocumentoConceptoCorreccionSeleccionarSerializer

    @extend_schema(
        parameters=_SELECCIONAR_PARAMS,
        responses=GenDocumentoConceptoCorreccionSeleccionarSerializer(many=True),
    )
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenDocumentoConceptoCorreccion.objects.order_by('id')
        documento_clase_id = request.query_params.get('documento_clase_id')
        if documento_clase_id is not None:
            if not documento_clase_id.isdigit():
                return Response(
                    {'detail': 'El parámetro documento_clase_id debe ser un número entero.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = qs.filter(documento_clase_id=documento_clase_id)
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenDocumentoConceptoCorreccionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
