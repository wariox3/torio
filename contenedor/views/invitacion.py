import logging
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnInvitacion
from contenedor.serializers import CtnInvitacionAceptarSerializer, CtnInvitacionSerializer
from seguridad.models import SegUsuarioCliente
from utilidades.zinc import Zinc

logger = logging.getLogger(__name__)

_SALT_INVITACION = 'ctn-invitacion'
_HORAS_EXPIRACION = 72

_RespuestaDetalle = inline_serializer(
    name='InvitacionDetailResponse',
    fields={'detail': serializers.CharField()},
)


@extend_schema(tags=['Invitación'])
class CtnInvitacionViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CtnInvitacionSerializer

    @extend_schema(
        summary='Invitar usuario al contenedor',
        description=(
            'Envía una invitación por correo al usuario indicado. '
            'Solo el owner del contenedor puede invitar. '
            'Si ya existe una invitación pendiente para ese correo, se reenvía con un nuevo token.'
        ),
        request=CtnInvitacionSerializer,
        responses={
            201: CtnInvitacionSerializer,
            400: OpenApiResponse(_RespuestaDetalle, description='El usuario ya es miembro'),
            403: OpenApiResponse(_RespuestaDetalle, description='Solo el owner puede invitar'),
        },
    )
    def create(self, request):
        serializador = CtnInvitacionSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        cliente = serializador.validated_data['cliente']
        correo = serializador.validated_data['correo'].lower()

        if cliente.owner_id != request.user.id:
            return Response(
                {'detail': 'Solo el owner del contenedor puede invitar usuarios.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if SegUsuarioCliente.objects.filter(usuario__email=correo, cliente=cliente).exists():
            return Response(
                {'detail': 'Este usuario ya es miembro del contenedor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = signing.dumps(correo, salt=_SALT_INVITACION)
        fecha_expira = timezone.now() + timedelta(hours=_HORAS_EXPIRACION)

        invitacion, _ = CtnInvitacion.objects.update_or_create(
            cliente=cliente,
            correo=correo,
            defaults={
                'invitado_por': request.user,
                'estado': CtnInvitacion.ESTADO_PENDIENTE,
                'fecha_expira': fecha_expira,
                'token': token,
            },
        )

        link = f'{settings.FRONTEND_URL}/auth/invitacion?token={token}'
        html = (
            f'<h1>Te han invitado a {cliente.nombre}</h1>'
            f'<p>{request.user.nombre_corto} te ha invitado a colaborar en <strong>{cliente.nombre}</strong>.</p>'
            f'<p>Haz clic en el siguiente enlace para aceptar (válido por {_HORAS_EXPIRACION} horas):</p>'
            f'<a href="{link}">Aceptar invitación</a>'
        )
        try:
            Zinc().correo(correo, f'Invitación a {cliente.nombre}', html)
        except Exception as e:
            logger.warning('No se pudo enviar correo de invitación a %s: %s', correo, e)

        return Response(CtnInvitacionSerializer(invitacion).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Aceptar invitación',
        description=(
            'El usuario autenticado acepta la invitación identificada por el token. '
            'Su correo debe coincidir con el de la invitación. Válido por 72 horas.'
        ),
        request=CtnInvitacionAceptarSerializer,
        responses={
            200: _RespuestaDetalle,
            400: OpenApiResponse(_RespuestaDetalle, description='Token inválido, expirado o correo no coincide'),
            409: OpenApiResponse(_RespuestaDetalle, description='Ya es miembro de este contenedor'),
        },
    )
    @action(detail=False, methods=['post'], url_path='aceptar')
    def aceptar(self, request):
        serializador = CtnInvitacionAceptarSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        token = serializador.validated_data['token']

        try:
            correo = signing.loads(token, salt=_SALT_INVITACION, max_age=_HORAS_EXPIRACION * 3600)
        except signing.SignatureExpired:
            return Response({'detail': 'La invitación ha expirado.'}, status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'detail': 'Token de invitación inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.email != correo:
            return Response(
                {'detail': 'Esta invitación no corresponde a tu cuenta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invitacion = CtnInvitacion.objects.select_related('cliente').get(
                token=token,
                estado=CtnInvitacion.ESTADO_PENDIENTE,
            )
        except CtnInvitacion.DoesNotExist:
            return Response(
                {'detail': 'Invitación no encontrada o ya procesada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if SegUsuarioCliente.objects.filter(usuario=request.user, cliente=invitacion.cliente).exists():
            return Response({'detail': 'Ya eres miembro de este contenedor.'}, status=status.HTTP_409_CONFLICT)

        SegUsuarioCliente.objects.create(usuario=request.user, cliente=invitacion.cliente)
        invitacion.estado = CtnInvitacion.ESTADO_ACEPTADA
        invitacion.save(update_fields=['estado'])

        return Response({'detail': f'Ahora eres miembro de {invitacion.cliente.nombre}.'})
