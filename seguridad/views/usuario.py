import logging

from django.conf import settings
from django.core import signing
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from seguridad.models import SegUsuario
from seguridad.serializers import SegUsuarioSerializer
from utilidades.turnstile import verify_turnstile
from utilidades.zinc import Zinc

logger = logging.getLogger(__name__)

_SALT_VERIFICACION = 'seg-verificacion-email'
_TIEMPO_VERIFICACION = 72 * 3600  # 72 horas

_SALT_RECUPERAR = 'seg-recuperar-clave'
_TIEMPO_RECUPERAR = 3600  # 1 hora

_RespuestaDetalle = inline_serializer(
    name='UsuarioDetailResponse',
    fields={'detail': serializers.CharField()},
)


class SegUsuarioViewSet(viewsets.ModelViewSet):
    queryset = SegUsuario.objects.all()
    serializer_class = SegUsuarioSerializer

    def get_permissions(self):
        return super().get_permissions()

    def get_throttles(self):
        scopes = {
            'create': 'registro',
            'recuperar_clave': 'recuperar_clave',
            'restablecer_clave': 'restablecer_clave',
        }
        if self.action in scopes:
            self.throttle_scope = scopes[self.action]
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        self.permission_classes = [AllowAny]
        self.authentication_classes = []
        verify_turnstile(request.data.get('turnstile_token', ''), request.META.get('REMOTE_ADDR'))
        serializador = self.get_serializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        usuario = serializador.save()

        token = signing.dumps(usuario.email, salt=_SALT_VERIFICACION)
        verificacion_url = f'{settings.FRONTEND_URL}/auth/verify-email?token={token}'
        contenido_html = (
            f'<h1>¡Hola {usuario.nombre_corto}!</h1>'
            f'<p>Por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>'
            f'<a href="{verificacion_url}">Verificar cuenta</a>'
        )
        try:
            Zinc().correo(usuario.email, 'Verifica tu cuenta', contenido_html)
        except Exception as e:
            logger.warning('No se pudo enviar correo de verificación a %s: %s', usuario.email, e)

        cabeceras = self.get_success_headers(serializador.data)
        return Response(serializador.data, status=status.HTTP_201_CREATED, headers=cabeceras)

    @extend_schema(
        tags=['Autenticación'],
        summary='Verificar email',
        description='Activa la cuenta con el token enviado al correo. Válido 72 horas.',
        request=inline_serializer(
            name='VerificacionTokenRequest',
            fields={'token': serializers.CharField()},
        ),
        responses={
            200: _RespuestaDetalle,
            400: OpenApiResponse(_RespuestaDetalle, description='Token inválido o expirado'),
            404: OpenApiResponse(_RespuestaDetalle, description='Usuario no encontrado'),
        },
    )
    @action(detail=False, methods=['post'], url_path='verificar-email', permission_classes=[AllowAny], authentication_classes=[])
    def verificar_email(self, request):
        token = request.data.get('token', '').strip()
        if not token:
            return Response({'detail': 'Token requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            correo = signing.loads(token, salt=_SALT_VERIFICACION, max_age=_TIEMPO_VERIFICACION)
        except signing.SignatureExpired:
            return Response(
                {'detail': 'El enlace ha expirado. Solicita uno nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response({'detail': 'Token inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = SegUsuario.objects.get(email=correo)
        except SegUsuario.DoesNotExist:
            return Response({'detail': 'Usuario no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if usuario.is_verified:
            return Response({'detail': 'La cuenta ya estaba verificada.'})

        usuario.is_verified = True
        usuario.save(update_fields=['is_verified'])
        return Response({'detail': 'Cuenta verificada. Ya puedes iniciar sesión.'})

    @extend_schema(
        tags=['Autenticación'],
        summary='Reenviar email de verificación',
        description='Reenvía el correo de verificación si la cuenta aún no está activa.',
        request=inline_serializer(
            name='ReenviarVerificacionRequest',
            fields={'email': serializers.EmailField()},
        ),
        responses={200: _RespuestaDetalle},
    )
    @action(detail=False, methods=['post'], url_path='reenviar-verificacion',
            permission_classes=[AllowAny], authentication_classes=[])
    def reenviar_verificacion(self, request):
        correo = request.data.get('email', '').strip().lower()
        if not correo:
            return Response({'detail': 'Email requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        _RESPUESTA_GENERICA = Response(
            {'detail': 'Si la cuenta existe, recibirás un correo de verificación.'}
        )

        try:
            usuario = SegUsuario.objects.get(email=correo)
        except SegUsuario.DoesNotExist:
            return _RESPUESTA_GENERICA

        if usuario.is_verified:
            return _RESPUESTA_GENERICA

        token = signing.dumps(usuario.email, salt=_SALT_VERIFICACION)
        verificacion_url = f'{settings.FRONTEND_URL}/auth/verify-email?token={token}'
        contenido_html = (
            f'<h1>¡Hola {usuario.nombre_corto}!</h1>'
            f'<p>Por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>'
            f'<a href="{verificacion_url}">Verificar cuenta</a>'
        )
        try:
            Zinc().correo(usuario.email, 'Verifica tu cuenta', contenido_html)
        except Exception as e:
            logger.warning('No se pudo enviar correo de verificación a %s: %s', usuario.email, e)

        return _RESPUESTA_GENERICA

    @extend_schema(exclude=True)
    @action(detail=False, methods=['post'], url_path='recuperar-clave',
            permission_classes=[AllowAny], authentication_classes=[])
    def recuperar_clave(self, request):
        verify_turnstile(request.data.get('turnstile_token', ''), request.META.get('REMOTE_ADDR'))
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'detail': 'Email requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        _RESPUESTA_GENERICA = Response(
            {'detail': 'Si el correo existe, recibirás las instrucciones para recuperar tu clave.'}
        )

        try:
            usuario = SegUsuario.objects.get(email=email)
        except SegUsuario.DoesNotExist:
            return _RESPUESTA_GENERICA

        if not usuario.is_verified:
            return Response(
                {'detail': 'Cuenta no verificada.', 'is_verified': False},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = signing.dumps(email, salt=_SALT_RECUPERAR)
        reset_link = f'{settings.FRONTEND_URL}/auth/restablecer-clave?token={token}'
        html_content = (
            f'<h1>Recuperación de clave</h1>'
            f'<p>Recibimos una solicitud para restablecer la clave de tu cuenta.</p>'
            f'<p>Haz clic en el siguiente enlace para crear una nueva clave:</p>'
            f'<a href="{reset_link}">Restablecer clave</a>'
            f'<p>Si no solicitaste esto, ignora este correo.</p>'
        )
        try:
            Zinc().correo(email, 'Recuperación de clave', html_content)
        except Exception as e:
            logger.warning('No se pudo enviar correo de recuperación a %s: %s', email, e)

        return _RESPUESTA_GENERICA

    @extend_schema(exclude=True)
    @action(detail=False, methods=['post'], url_path='restablecer-clave',
            permission_classes=[AllowAny], authentication_classes=[])
    def restablecer_clave(self, request):
        verify_turnstile(request.data.get('turnstile_token', ''), request.META.get('REMOTE_ADDR'))
        token = request.data.get('token', '').strip()
        nueva_clave = request.data.get('nueva_clave', '')

        if not token or not nueva_clave:
            return Response(
                {'detail': 'Token y nueva_clave son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(nueva_clave) < 8:
            return Response(
                {'detail': 'La clave debe tener al menos 8 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            email = signing.loads(token, salt=_SALT_RECUPERAR, max_age=_TIEMPO_RECUPERAR)
        except signing.SignatureExpired:
            return Response(
                {'detail': 'El enlace ha expirado. Solicita uno nuevo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except signing.BadSignature:
            return Response({'detail': 'Token inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = SegUsuario.objects.get(email=email)
        except SegUsuario.DoesNotExist:
            return Response({'detail': 'Token inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        usuario.set_password(nueva_clave)
        usuario.save(update_fields=['password'])
        return Response({'detail': 'Clave restablecida correctamente.'})
