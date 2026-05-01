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
from utilidades.zinc import Zinc

logger = logging.getLogger(__name__)

_SALT = 'seg-verificacion-email'
_MAX_AGE = 72 * 3600  # 72 horas

_DetailResponse = inline_serializer(
    name='UsuarioDetailResponse',
    fields={'detail': serializers.CharField()},
)


class SegUsuarioViewSet(viewsets.ModelViewSet):
    queryset = SegUsuario.objects.all()
    serializer_class = SegUsuarioSerializer

    def get_permissions(self):
        if self.action in ('create', 'verificar_email', 'reenviar_verificacion'):
            return [AllowAny()]
        return super().get_permissions()

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'registro'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario = serializer.save()

        token = signing.dumps(usuario.email, salt=_SALT)
        verificacion_url = f'{settings.FRONTEND_URL}/auth/verify-email?token={token}'
        html_content = (
            f'<h1>¡Hola {usuario.nombre_corto}!</h1>'
            f'<p>Por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>'
            f'<a href="{verificacion_url}">Verificar cuenta</a>'
        )
        try:
            Zinc().correo(usuario.email, 'Verifica tu cuenta', html_content)
        except Exception as e:
            logger.warning('No se pudo enviar correo de verificación a %s: %s', usuario.email, e)

        headers = self.get_success_headers(serializer.data)
        return Response(
            {**serializer.data, 'verificacion_url': verificacion_url},
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @extend_schema(
        tags=['Autenticación'],
        summary='Verificar email',
        description='Activa la cuenta con el token enviado al correo. Válido 72 horas.',
        request=inline_serializer(
            name='VerificacionTokenRequest',
            fields={'token': serializers.CharField()},
        ),
        responses={
            200: _DetailResponse,
            400: OpenApiResponse(_DetailResponse, description='Token inválido o expirado'),
            404: OpenApiResponse(_DetailResponse, description='Usuario no encontrado'),
        },
    )
    @action(detail=False, methods=['post'], url_path='verificar-email')
    def verificar_email(self, request):
        token = request.data.get('token', '').strip()
        if not token:
            return Response({'detail': 'Token requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            email = signing.loads(token, salt=_SALT, max_age=_MAX_AGE)
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
        responses={
            200: _DetailResponse,
            400: OpenApiResponse(_DetailResponse, description='Cuenta ya verificada'),
        },
    )
    @action(detail=False, methods=['post'], url_path='reenviar-verificacion')
    def reenviar_verificacion(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'detail': 'Email requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = SegUsuario.objects.get(email=email)
        except SegUsuario.DoesNotExist:
            return Response({'detail': 'No existe una cuenta con este correo.'}, status=status.HTTP_404_NOT_FOUND)

        if usuario.is_verified:
            return Response(
                {'detail': 'Esta cuenta ya está verificada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = signing.dumps(usuario.email, salt=_SALT)
        verificacion_url = f'{settings.FRONTEND_URL}/auth/verify-email?token={token}'
        html_content = (
            f'<h1>¡Hola {usuario.nombre_corto}!</h1>'
            f'<p>Por favor verifica tu cuenta haciendo clic en el siguiente enlace.</p>'
            f'<a href="{verificacion_url}">Verificar cuenta</a>'
        )
        try:
            Zinc().correo(usuario.email, 'Verifica tu cuenta', html_content)
        except Exception as e:
            logger.warning('No se pudo enviar correo de verificación a %s: %s', usuario.email, e)
        return Response({'detail': 'Correo de verificación reenviado.'})
