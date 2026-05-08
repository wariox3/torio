from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnCiudad
from contenedor.serializers import CtnCiudadListaSerializer, CtnCiudadSerializer

_SEARCH_PARAMS = [
    OpenApiParameter('estado', int, description='Filtrar por ID de estado'),
    OpenApiParameter('search', str, description='Buscar por nombre (mínimo 2 caracteres, retorna 10 resultados)'),
]


@extend_schema(tags=['Ciudad'])
class CtnCiudadViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_serializer_class(self):
        if self.action == 'list':
            return CtnCiudadListaSerializer
        return CtnCiudadSerializer

    @extend_schema(parameters=_SEARCH_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = CtnCiudad.objects.select_related('estado').all()
        estado = self.request.query_params.get('estado')
        search = self.request.query_params.get('search', '').strip()
        if estado:
            qs = qs.filter(estado_id=estado)
        if search:
            qs = qs.filter(nombre__icontains=search)[:10]
        return qs
