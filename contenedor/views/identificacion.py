from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnIdentificacion
from contenedor.serializers import CtnIdentificacionListaSerializer, CtnIdentificacionSerializer

_SEARCH_PARAMS = [
    OpenApiParameter('pais', str, description='Filtrar por código de país'),
    OpenApiParameter('search', str, description='Buscar por nombre (retorna 10 resultados)'),
]


@extend_schema(tags=['Identificacion'])
class CtnIdentificacionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        if self.action == 'list':
            return CtnIdentificacionListaSerializer
        return CtnIdentificacionSerializer

    @extend_schema(parameters=_SEARCH_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = CtnIdentificacion.objects.select_related('pais').order_by('orden', 'nombre')
        pais = self.request.query_params.get('pais')
        search = self.request.query_params.get('search', '').strip()
        if pais:
            qs = qs.filter(pais_id=pais)
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        return qs
