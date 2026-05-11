from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnSuscripcionTipo
from contenedor.serializers import CtnSuscripcionTipoSerializer

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
    OpenApiParameter('suscripcion_clase_id', int, description='Filtrar por clase de suscripción'),
    OpenApiParameter('suscripcion_categoria_id', int, description='Filtrar por categoría de suscripción'),
]


@extend_schema(tags=['SuscripcionTipo'])
class CtnSuscripcionTipoViewSet(viewsets.ModelViewSet):
    serializer_class = CtnSuscripcionTipoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnSuscripcionTipo.objects.order_by('id')
        search = self.request.query_params.get('search', '').strip()
        suscripcion_clase_id = self.request.query_params.get('suscripcion_clase_id')
        suscripcion_categoria_id = self.request.query_params.get('suscripcion_categoria_id')
        if search:
            qs = qs.filter(nombre__icontains=search)
        if suscripcion_clase_id:
            qs = qs.filter(suscripcion_clase_id=suscripcion_clase_id)
        if suscripcion_categoria_id:
            qs = qs.filter(suscripcion_categoria_id=suscripcion_categoria_id)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
