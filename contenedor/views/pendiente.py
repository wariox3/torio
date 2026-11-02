from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnPendiente
from contenedor.serializers.pendiente import CtnPendienteSerializer
from seguridad.models import SegUsuarioAplicacion, SegUsuarioCliente


@extend_schema(tags=['Pendiente'])
class CtnPendienteViewSet(viewsets.GenericViewSet):
    serializer_class = CtnPendienteSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Pendientes de mis contenedores',
        description=(
            'Lo que `analizar_pendientes` encontró en los contenedores de los que el '
            'usuario es miembro, solo de sus aplicaciones (`SegUsuarioAplicacion`) y '
            'de contenedores con suscripción vigente. Sin paginar.\n\n'
            'Con `cliente`, solo los de ese contenedor; uno ajeno devuelve `[]`, igual '
            'que uno sin pendientes.'
        ),
        parameters=[OpenApiParameter('cliente', OpenApiTypes.INT, required=False)],
        responses=CtnPendienteSerializer(many=True),
    )
    def list(self, request):
        cliente = request.query_params.get('cliente')
        if cliente is not None and not cliente.isdigit():
            raise ValidationError({'detail': 'El parámetro cliente debe ser un número.'})

        clientes = SegUsuarioCliente.objects.filter(usuario=request.user)
        if cliente is not None:
            clientes = clientes.filter(cliente_id=int(cliente))
        aplicaciones = SegUsuarioAplicacion.objects.filter(usuario=request.user)

        # Un contenedor vencido no se analiza: sus pendientes quedan de la última
        # corrida, así que no se muestran.
        pendientes = (
            CtnPendiente.objects.filter(
                cliente_id__in=clientes.values('cliente_id'),
                pendiente_tipo__aplicacion_id__in=aplicaciones.values('aplicacion_id'),
                cantidad__gt=0,
                cliente__suscripcion__fecha_fin__gte=timezone.localdate(),
            )
            .select_related('cliente', 'pendiente_tipo__aplicacion')
            .order_by('cliente__nombre', 'cliente_id', 'pendiente_tipo_id')
        )
        return Response(CtnPendienteSerializer(pendientes, many=True).data)
