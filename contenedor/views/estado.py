from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnEstado
from contenedor.serializers import CtnEstadoListaSerializer, CtnEstadoSerializer

_SEARCH_PARAMS = [
    OpenApiParameter('pais', str, description='Filtrar por código de país'),
    OpenApiParameter('search', str, description='Buscar por nombre (mínimo 2 caracteres, retorna 10 resultados)'),
]


@extend_schema(tags=['Estado'])
class CtnEstadoViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        if self.action == 'list':
            return CtnEstadoListaSerializer
        return CtnEstadoSerializer

    @extend_schema(parameters=_SEARCH_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = CtnEstado.objects.select_related('pais').all()
        pais = self.request.query_params.get('pais')
        search = self.request.query_params.get('search', '').strip()
        if pais:
            qs = qs.filter(pais_id=pais)
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        return qs
