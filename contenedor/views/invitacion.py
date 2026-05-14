import logging

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor.models import CtnInvitacion
from contenedor.serializers import CtnInvitacionCrearSerializer, CtnInvitacionSerializer
from seguridad.models import SegUsuario, SegUsuarioCliente
from utilidades.zinc import Zinc

logger = logging.getLogger(__name__)

_RespuestaDetalle = inline_serializer(
    name='InvitacionDetailResponse',
    fields={'detail': serializers.CharField()},
)


@extend_schema(tags=['Invitación'])
class CtnInvitacionViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CtnInvitacionSerializer

    def get_queryset(self):
        return CtnInvitacion.objects.filter(usuario_invitado=self.request.user)

    @extend_schema(
        summary='Invitar usuario al contenedor',
        description='Envía una invitación a un usuario registrado. Solo el owner puede invitar.',
        request=CtnInvitacionCrearSerializer,
        responses={
            201: CtnInvitacionSerializer,
            400: OpenApiResponse(_RespuestaDetalle, description='El usuario ya es miembro'),
            403: OpenApiResponse(_RespuestaDetalle, description='Solo el owner puede invitar'),
            404: OpenApiResponse(_RespuestaDetalle, description='Usuario no encontrado'),
        },
    )
    def create(self, request):
        serializador = CtnInvitacionCrearSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        cliente = serializador.validated_data['cliente']
        usuario_id = serializador.validated_data['usuario_id']
        rol = serializador.validated_data.get('rol')

        if cliente.owner_id != request.user.id:
            return Response(
                {'detail': 'Solo el owner del contenedor puede invitar usuarios.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            usuario = SegUsuario.objects.get(pk=usuario_id)
        except SegUsuario.DoesNotExist:
            return Response({'detail': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if not usuario.is_verified:
            return Response(
                {'detail': 'El usuario no ha verificado su cuenta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if SegUsuarioCliente.objects.filter(usuario=usuario, cliente=cliente).exists():
            return Response(
                {'detail': 'El usuario ya es miembro del contenedor.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if CtnInvitacion.objects.filter(
            cliente=cliente,
            usuario_invitado=usuario,
            estado=CtnInvitacion.ESTADO_PENDIENTE,
        ).exists():
            return Response(
                {'detail': 'Ya existe una invitación pendiente para este usuario.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitacion = CtnInvitacion.objects.create(
            cliente=cliente,
            usuario_invitado=usuario,
            usuario=request.user,
            rol=rol,
            estado=CtnInvitacion.ESTADO_PENDIENTE,
        )

        link = f'{settings.FRONTEND_URL}/invitaciones'
        html = (
            f'<h1>Te han invitado a {cliente.nombre}</h1>'
            f'<p>{request.user.nombre_corto} te ha invitado a colaborar en '
            f'<strong>{cliente.nombre}</strong>.</p>'
            f'<p>Inicia sesión y acepta la invitación desde tu panel:</p>'
            f'<a href="{link}">Ver invitaciones</a>'
        )
        try:
            Zinc().correo(usuario.email, f'Invitación a {cliente.nombre}', html)
        except Exception as e:
            logger.warning('No se pudo enviar correo de invitación a %s: %s', usuario.email, e)

        return Response(CtnInvitacionSerializer(invitacion).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Invitaciones pendientes',
        description='Retorna las invitaciones pendientes del usuario autenticado.',
        responses={200: CtnInvitacionSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='pendiente')
    def pendiente(self, request):
        qs = self.get_queryset().filter(
            estado=CtnInvitacion.ESTADO_PENDIENTE
        ).select_related('cliente')
        return Response(CtnInvitacionSerializer(qs, many=True).data)

    @extend_schema(
        summary='Aceptar invitación',
        description='El usuario autenticado acepta una invitación pendiente.',
        responses={
            200: _RespuestaDetalle,
            403: OpenApiResponse(_RespuestaDetalle, description='La invitación no te pertenece'),
            404: OpenApiResponse(_RespuestaDetalle, description='Invitación no encontrada'),
            409: OpenApiResponse(_RespuestaDetalle, description='Ya eres miembro'),
        },
    )
    @action(detail=True, methods=['post'], url_path='aceptar')
    def aceptar(self, request, pk=None):
        try:
            invitacion = CtnInvitacion.objects.select_related('cliente').get(pk=pk)
        except CtnInvitacion.DoesNotExist:
            return Response({'detail': 'Invitación no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        if invitacion.usuario_invitado_id != request.user.id:
            return Response({'detail': 'Esta invitación no te pertenece.'}, status=status.HTTP_403_FORBIDDEN)

        if invitacion.estado != CtnInvitacion.ESTADO_PENDIENTE:
            return Response({'detail': 'La invitación ya fue procesada.'}, status=status.HTTP_409_CONFLICT)

        if SegUsuarioCliente.objects.filter(usuario=request.user, cliente=invitacion.cliente).exists():
            return Response({'detail': 'Ya eres miembro de este contenedor.'}, status=status.HTTP_409_CONFLICT)

        SegUsuarioCliente.objects.create(usuario=request.user, cliente=invitacion.cliente, rol=invitacion.rol)
        invitacion.estado = CtnInvitacion.ESTADO_ACEPTADA
        invitacion.save(update_fields=['estado'])

        return Response({'detail': f'Ahora eres miembro de {invitacion.cliente.nombre}.'})

    @extend_schema(
        summary='Rechazar invitación',
        description='El usuario autenticado rechaza una invitación pendiente.',
        responses={
            200: _RespuestaDetalle,
            403: OpenApiResponse(_RespuestaDetalle, description='La invitación no te pertenece'),
            404: OpenApiResponse(_RespuestaDetalle, description='Invitación no encontrada'),
        },
    )
    @action(detail=True, methods=['post'], url_path='rechazar')
    def rechazar(self, request, pk=None):
        try:
            invitacion = CtnInvitacion.objects.get(pk=pk)
        except CtnInvitacion.DoesNotExist:
            return Response({'detail': 'Invitación no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        if invitacion.usuario_invitado_id != request.user.id:
            return Response({'detail': 'Esta invitación no te pertenece.'}, status=status.HTTP_403_FORBIDDEN)

        if invitacion.estado != CtnInvitacion.ESTADO_PENDIENTE:
            return Response({'detail': 'La invitación ya fue procesada.'}, status=status.HTTP_409_CONFLICT)

        invitacion.estado = CtnInvitacion.ESTADO_RECHAZADA
        invitacion.save(update_fields=['estado'])

        return Response({'detail': 'Invitación rechazada.'})
