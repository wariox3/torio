from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets

from general.models import GenLog
from general.serializers.log import GenLogSerializer

_LISTAR_PARAMS = [
    OpenApiParameter('modelo', int, description='ID de gen_modelo'),
    OpenApiParameter('objeto_id', str, description='ID del registro auditado'),
    OpenApiParameter('accion', int, description='ID de gen_accion'),
    OpenApiParameter('usuario_id', int, description='ID del usuario que ejecutó la acción'),
    OpenApiParameter('fecha_desde', str, description='Fecha desde (ISO)'),
    OpenApiParameter('fecha_hasta', str, description='Fecha hasta (ISO)'),
]


@extend_schema(tags=['Log'])
class GenLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = GenLogSerializer
    queryset = GenLog.objects.select_related('accion', 'modelo').order_by('-fecha')

    @extend_schema(parameters=_LISTAR_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (modelo := params.get('modelo')):
            qs = qs.filter(modelo_id=modelo)
        if (objeto_id := params.get('objeto_id')):
            qs = qs.filter(objeto_id=objeto_id)
        if (accion := params.get('accion')):
            qs = qs.filter(accion_id=accion)
        if (usuario_id := params.get('usuario_id')):
            qs = qs.filter(usuario_id=usuario_id)
        if (fecha_desde := params.get('fecha_desde')):
            qs = qs.filter(fecha__gte=fecha_desde)
        if (fecha_hasta := params.get('fecha_hasta')):
            qs = qs.filter(fecha__lte=fecha_hasta)
        return qs
