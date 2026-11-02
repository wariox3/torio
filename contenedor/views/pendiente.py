from django.db.models import Exists, OuterRef
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnPendiente
from contenedor.serializers.pendiente import CtnPendienteSerializer
from seguridad.models import SegUsuarioClienteAplicacion


@extend_schema(tags=['Pendiente'])
class CtnPendienteViewSet(viewsets.GenericViewSet):
    serializer_class = CtnPendienteSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Pendientes de mis contenedores',
        description=(
            'Lo que `analizar_pendientes` encontró en los contenedores de los que el '
            'usuario es miembro, solo de las aplicaciones que tiene en cada uno '
            '(`SegUsuarioClienteAplicacion`) y de contenedores con suscripción '
            'vigente. Sin paginar.\n\n'
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

        # La membresía del usuario en el contenedor del pendiente tiene su aplicación.
        # Sin membresía no hay fila, así que esto también limita a sus contenedores.
        con_aplicacion = SegUsuarioClienteAplicacion.objects.filter(
            usuario_cliente__usuario=request.user,
            usuario_cliente__cliente_id=OuterRef('cliente_id'),
            aplicacion_id=OuterRef('pendiente_tipo__aplicacion_id'),
        )

        # Un contenedor vencido no se analiza: sus pendientes quedan de la última
        # corrida, así que no se muestran.
        pendientes = (
            CtnPendiente.objects.filter(
                Exists(con_aplicacion),
                cantidad__gt=0,
                cliente__suscripcion__fecha_fin__gte=timezone.localdate(),
            )
            .select_related('cliente', 'pendiente_tipo__aplicacion')
            .order_by('cliente__nombre', 'cliente_id', 'pendiente_tipo_id')
        )
        if cliente is not None:
            pendientes = pendientes.filter(cliente_id=int(cliente))
        return Response(CtnPendienteSerializer(pendientes, many=True).data)
