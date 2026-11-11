from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnPendiente
from contenedor.serializers.pendiente import CtnPendienteSerializer
from seguridad.models import SegUsuarioCliente, SegUsuarioClienteGrupo


@extend_schema(tags=['Pendiente'])
class CtnPendienteViewSet(viewsets.GenericViewSet):
    serializer_class = CtnPendienteSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Pendientes de mis contenedores',
        description=(
            'Lo que `analizar_pendientes` encontró en los contenedores de los que el '
            'usuario es miembro, de contenedores con suscripción vigente, y solo los '
            'de los grupos que tiene en cada uno (`SegUsuarioClienteGrupo`); si es '
            'superusuario del contenedor, todos. Sin paginar.\n\n'
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

        # La membresía del usuario en el contenedor del pendiente es
        # propietaria, administradora o de soporte, o tiene el grupo del tipo. Sin membresía no hay fila, así
        # que esto también limita a sus contenedores.
        es_superusuario = SegUsuarioCliente.objects.filter(
            Q(propietario=True) | Q(administrador=True) | Q(soporte=True),
            usuario=request.user, cliente_id=OuterRef('cliente_id'),
        )
        con_grupo = SegUsuarioClienteGrupo.objects.filter(
            usuario_cliente__usuario=request.user,
            usuario_cliente__cliente_id=OuterRef('cliente_id'),
            grupo_id=OuterRef('pendiente_tipo__grupo_id'),
        )

        # Un contenedor vencido no se analiza: sus pendientes quedan de la última
        # corrida, así que no se muestran.
        pendientes = (
            CtnPendiente.objects.filter(
                Q(Exists(es_superusuario)) | Q(Exists(con_grupo)),
                cantidad__gt=0,
                cliente__suscripcion__fecha_fin__gte=timezone.localdate(),
            )
            .select_related('cliente', 'pendiente_tipo__grupo')
            .order_by('cliente__nombre', 'cliente_id', 'pendiente_tipo_id')
        )
        if cliente is not None:
            pendientes = pendientes.filter(cliente_id=int(cliente))
        return Response(CtnPendienteSerializer(pendientes, many=True).data)
