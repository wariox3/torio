import logging

from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from tenant_users.tenants.models import ExistsError

from contenedor.models import CtnInvitacion
from contenedor.serializers import CtnInvitacionClienteSerializer, CtnInvitacionCrearSerializer, CtnInvitacionSerializer
from seguridad.models import CAMPOS_ACCESO, SegUsuario, SegUsuarioCliente
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
        grupos = serializador.validated_data.get('grupos') or []
        accesos = {
            campo: serializador.validated_data.get(campo, False)
            for campo in CAMPOS_ACCESO
        }

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

        invitacion_existente = CtnInvitacion.objects.filter(
            cliente=cliente,
            usuario_invitado=usuario,
        ).first()

        if invitacion_existente:
            if invitacion_existente.estado == CtnInvitacion.ESTADO_PENDIENTE:
                return Response(
                    {'detail': 'Ya existe una invitación pendiente para este usuario.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            invitacion_existente.estado = CtnInvitacion.ESTADO_PENDIENTE
            invitacion_existente.usuario = request.user
            invitacion_existente.rol = rol
            # Los accesos se reemplazan igual que los grupos: la reinvitación
            # manda, no se acumula sobre lo que decía la invitación anterior.
            for campo, valor in accesos.items():
                setattr(invitacion_existente, campo, valor)
            invitacion_existente.save(
                update_fields=['estado', 'usuario', 'rol', *accesos],
            )
            invitacion = invitacion_existente
        else:
            invitacion = CtnInvitacion.objects.create(
                cliente=cliente,
                usuario_invitado=usuario,
                usuario=request.user,
                rol=rol,
                estado=CtnInvitacion.ESTADO_PENDIENTE,
                **accesos,
            )

        # Los grupos se fijan en los dos caminos: al reinvitar hay que reemplazar
        # los de la invitación anterior, no acumularlos.
        invitacion.grupos.set(grupos)

        link = f'{settings.FRONTEND_CUENTA_URL}/invitaciones'
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
        summary='Invitaciones pendientes del usuario autenticado',
        description='Retorna las invitaciones pendientes recibidas por el usuario autenticado.',
        responses={200: CtnInvitacionSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='pendiente-usuario')
    def pendiente_usuario(self, request):
        qs = self.get_queryset().filter(
            estado=CtnInvitacion.ESTADO_PENDIENTE
        ).select_related('cliente', 'rol', 'usuario')
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CtnInvitacionSerializer(pagina, many=True).data)

    @extend_schema(
        summary='Invitaciones pendientes de un cliente',
        description='Retorna las invitaciones pendientes enviadas desde un cliente.',
        parameters=[
            OpenApiParameter('cliente_id', int, required=True, description='ID del cliente'),
        ],
        responses={
            200: CtnInvitacionSerializer(many=True),
            400: OpenApiResponse(_RespuestaDetalle, description='cliente_id requerido'),
        },
    )
    @action(detail=False, methods=['get'], url_path='pendiente-cliente')
    def pendiente_cliente(self, request):
        cliente_id = request.query_params.get('cliente_id')
        if not cliente_id:
            return Response({'detail': 'cliente_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = CtnInvitacion.objects.filter(
            cliente_id=cliente_id,
            estado=CtnInvitacion.ESTADO_PENDIENTE,
        ).select_related('usuario_invitado', 'rol')
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CtnInvitacionClienteSerializer(pagina, many=True).data)

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
    @transaction.atomic
    def aceptar(self, request, pk=None):
        try:
            invitacion = CtnInvitacion.objects.select_related('cliente').get(pk=pk)
        except CtnInvitacion.DoesNotExist:
            return Response({'detail': 'Invitación no encontrada.'}, status=status.HTTP_404_NOT_FOUND)

        if invitacion.usuario_invitado_id != request.user.id:
            return Response({'detail': 'Esta invitación no te pertenece.'}, status=status.HTTP_403_FORBIDDEN)

        if invitacion.estado != CtnInvitacion.ESTADO_PENDIENTE:
            return Response({'detail': 'La invitación ya fue procesada.'}, status=status.HTTP_409_CONFLICT)

        # add_user vuelve a comprobar la membresía dentro de su transacción, así
        # que dos aceptaciones simultáneas terminan en 409 y no en un 500.
        try:
            invitacion.cliente.add_user(
                request.user,
                rol=invitacion.rol,
                grupos=list(invitacion.grupos.all()),
                accesos={campo: getattr(invitacion, campo) for campo in CAMPOS_ACCESO},
            )
        except ExistsError:
            return Response({'detail': 'Ya eres miembro de este contenedor.'}, status=status.HTTP_409_CONFLICT)

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

        invitacion.delete()
        return Response({'detail': 'Invitación rechazada.'}, status=status.HTTP_200_OK)
