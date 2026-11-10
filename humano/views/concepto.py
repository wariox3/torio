from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from humano.models import HumConcepto
from humano.serializers import HumConceptoSeleccionarSerializer, HumConceptoSerializer
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import FiltrosDinamicosMixin
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('concepto_tipo_id', int, description='Filtrar por ID de tipo de concepto'),
    OpenApiParameter('adicional', bool, description='Filtrar por adicional'),
    OpenApiParameter('operacion', int, description='Filtrar por operación: 1 suma, -1 resta, 0 neutro'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Concepto'])
class HumConceptoViewSet(FiltrosDinamicosMixin, viewsets.GenericViewSet):
    """Catálogo de conceptos: `seleccionar`, `lista` y `configuracion`, de solo lectura."""

    serializer_class = HumConceptoSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        return HumConcepto.objects.order_by('orden', 'id')

    @extend_schema(responses=HumConceptoSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=None)
    def configuracion(self, request):
        """Todos los conceptos, sin paginar ni filtrar: la pantalla de configuración los muestra completos."""
        qs = self.get_queryset().select_related(*HumConceptoSerializer.select_related_lista)
        return Response(HumConceptoSerializer(qs, many=True).data)

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

        operacion = request.query_params.get('operacion')
        if operacion is not None:
            try:
                qs = qs.filter(operacion=int(operacion))
            except ValueError:
                return Response({'detail': 'operacion debe ser un número entero.'}, status=status.HTTP_400_BAD_REQUEST)

        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumConceptoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
