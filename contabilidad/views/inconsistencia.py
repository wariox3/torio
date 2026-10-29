from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.models import ConInconsistencia
from contabilidad.serializers import ConInconsistenciaSerializer
from contabilidad.servicios.movimiento import TIPO_BASE_SOBRANTE
from utilidades.mixins import FiltrosDinamicosMixin


class ConInconsistenciaResolverRequestSerializer(serializers.Serializer):
    id = serializers.PrimaryKeyRelatedField(queryset=ConInconsistencia.objects.all())


@extend_schema(tags=['Inconsistencia'])
class ConInconsistenciaViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Las filas las escriben `periodo/analizar` y `periodo/bloquear`; acá solo se leen y se resuelven."""

    serializer_class = ConInconsistenciaSerializer

    def get_queryset(self):
        return ConInconsistencia.objects.select_related(
            *ConInconsistenciaSerializer.select_related_lista
        )

    @extend_schema(
        summary='Resolver automáticamente una inconsistencia',
        description=(
            'Corrige la inconsistencia si su tipo es `resolver_automatico` y la elimina. '
            'Por ahora solo resuelve "Sobra base" (tipo 8): pone en cero la base del '
            'movimiento. No cambia `estado_inconsistencia` del periodo: para eso hay que '
            'volver a analizarlo.'
        ),
        request=ConInconsistenciaResolverRequestSerializer,
        responses={204: None},
    )
    @action(detail=False, methods=['post'])
    def resolver(self, request):
        serializer = ConInconsistenciaResolverRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # Bloqueada para que dos peticiones simultáneas no la resuelvan dos veces: la
            # segunda espera a que la primera la elimine y ya no la encuentra.
            inconsistencia = (
                ConInconsistencia.objects
                .select_for_update(of=('self',))
                .select_related('inconsistencia_tipo', 'movimiento__periodo')
                .filter(pk=serializer.validated_data['id'].pk)
                .first()
            )
            if inconsistencia is None:
                raise ValidationError({'detail': 'La inconsistencia ya fue resuelta'})
            if not inconsistencia.inconsistencia_tipo.resolver_automatico:
                raise ValidationError({'detail': 'La inconsistencia no se puede resolver automáticamente'})
            if inconsistencia.inconsistencia_tipo_id != TIPO_BASE_SOBRANTE:
                raise ValidationError({
                    'detail': 'Todavía no hay resolución automática para este tipo de inconsistencia',
                })

            movimiento = inconsistencia.movimiento
            if movimiento is None:
                raise ValidationError({'detail': 'La inconsistencia no tiene movimiento asociado'})
            # Un periodo bloqueado es inmutable: corregirlo exige desbloquearlo primero.
            if movimiento.periodo.estado_bloqueado:
                raise ValidationError({'detail': 'El periodo del movimiento está bloqueado'})

            movimiento.base = 0
            movimiento.save(update_fields=['base'])
            inconsistencia.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
