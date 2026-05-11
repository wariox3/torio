from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnSuscripcion
from contenedor.serializers import CtnSuscripcionSerializer

_LIST_PARAMS = [
    OpenApiParameter('cliente_id', int, description='Filtrar por cliente'),
    OpenApiParameter('usuario_id', int, description='Filtrar por usuario'),
    OpenApiParameter('suscripcion_tipo_id', int, description='Filtrar por tipo de suscripción'),
]


@extend_schema(tags=['Suscripcion'])
class CtnSuscripcionViewSet(viewsets.ModelViewSet):
    serializer_class = CtnSuscripcionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CtnSuscripcion.objects.select_related('cliente', 'usuario', 'suscripcion_tipo').order_by('-fecha_inicio')
        cliente_id = self.request.query_params.get('cliente_id')
        usuario_id = self.request.query_params.get('usuario_id')
        suscripcion_tipo_id = self.request.query_params.get('suscripcion_tipo_id')
        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)
        if suscripcion_tipo_id:
            qs = qs.filter(suscripcion_tipo_id=suscripcion_tipo_id)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
