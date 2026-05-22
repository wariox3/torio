from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from general.models import GenIdentificacion
from general.serializers import GenIdentificacionSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('pais', str, description='Filtrar por código de país'),
    OpenApiParameter('tipo_persona_id', int, description='Filtrar por ID de tipo de persona'),
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Identificacion'])
class GenIdentificacionViewSet(viewsets.GenericViewSet):
    serializer_class = GenIdentificacionSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenIdentificacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenIdentificacion.objects.order_by('orden', 'nombre')
        pais = request.query_params.get('pais')
        tipo_persona = request.query_params.get('tipo_persona_id')
        search = request.query_params.get('search', '').strip()
        if pais:
            qs = qs.filter(pais_id=pais)
        if tipo_persona:
            qs = qs.filter(tipo_persona_id=tipo_persona)
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenIdentificacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
