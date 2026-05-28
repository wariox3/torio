from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from general.models import GenResponsabilidad
from general.serializers import GenResponsabilidadSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o código'),
]


@extend_schema(tags=['Responsabilidad'])
class GenResponsabilidadViewSet(viewsets.GenericViewSet):
    serializer_class = GenResponsabilidadSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenResponsabilidadSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenResponsabilidad.objects.filter(estado_activo=True).order_by('orden', 'nombre')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search) | qs.filter(codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = GenResponsabilidadSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
