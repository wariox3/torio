from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from seguridad.serializers import SegLoginSerializer, SegUsuarioMeSerializer
from utilidades.turnstile import verify_turnstile

_RespuestaDetalle = inline_serializer(
    name='DetailResponse',
    fields={'detail': serializers.CharField()},
)
_SolicitudRefresco = inline_serializer(
    name='RefreshRequest',
    fields={'refresh': serializers.CharField(required=False)},
)

_TIEMPO_MAXIMO_ACCESO = int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
_TIEMPO_MAXIMO_REFRESCO = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
_ROTAR = settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS', False)
_LISTA_NEGRA = settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION', False)


def _asignar_cookies_auth(respuesta, access_token, refresh_token=None):
    seguro = not settings.DEBUG
    dominio = settings.AUTH_COOKIE_DOMAIN
    respuesta.set_cookie('access_token', access_token, max_age=_TIEMPO_MAXIMO_ACCESO,
                         httponly=True, secure=seguro, samesite='Lax', domain=dominio)
    if refresh_token:
        respuesta.set_cookie('refresh_token', refresh_token, max_age=_TIEMPO_MAXIMO_REFRESCO,
                             httponly=True, secure=seguro, samesite='Lax', domain=dominio)


@extend_schema(
    tags=['Autenticación'],
    summary='Iniciar sesión',
    description='Valida credenciales y emite JWT en cookies httpOnly + body (para Bearer).',
    request=SegLoginSerializer,
    responses={
        200: SegUsuarioMeSerializer,
        401: OpenApiResponse(_RespuestaDetalle, description='Credenciales inválidas'),
        403: OpenApiResponse(_RespuestaDetalle, description='Cuenta no verificada'),
        429: OpenApiResponse(description='Demasiados intentos (rate limit 5/min)'),
    },
)
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        verify_turnstile(request.data.get('turnstile_token', ''), request.META.get('REMOTE_ADDR'))
        serializador = SegLoginSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        usuario = authenticate(
            request,
            username=serializador.validated_data['email'],
            password=serializador.validated_data['password'],
        )
        if usuario is None:
            return Response({'detail': 'Credenciales inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not usuario.is_verified:
            return Response(
                {'detail': 'Cuenta no verificada. Revisa tu correo para activarla.', 'verificado': False},
                status=status.HTTP_403_FORBIDDEN,
            )

        update_last_login(None, usuario)
        refresh = RefreshToken.for_user(usuario)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        data = SegUsuarioMeSerializer(usuario).data
        if settings.DEBUG:
            data['access_token'] = access_token
        respuesta = Response(data)
        _asignar_cookies_auth(respuesta, access_token, refresh_token)
        return respuesta


@extend_schema(
    tags=['Autenticación'],
    summary='Renovar access token',
    description='Renueva el access token. Si rotación está activa, también emite nuevo refresh y blacklistea el anterior.',
    request=_SolicitudRefresco,
    responses={
        200: _RespuestaDetalle,
        400: OpenApiResponse(_RespuestaDetalle, description='Refresh token no encontrado'),
        401: OpenApiResponse(_RespuestaDetalle, description='Token inválido o expirado'),
    },
)
class RefreshView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'refresh'

    def post(self, request):
        token = request.COOKIES.get('refresh_token') or request.data.get('refresh')
        if not token:
            return Response({'detail': 'Refresh token no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(token)
            access_token = str(refresh.access_token)

            new_refresh_token = None
            if _ROTAR:
                if _LISTA_NEGRA:
                    refresh.blacklist()
                refresh.set_jti()
                refresh.set_exp()
                refresh.set_iat()
                new_refresh_token = str(refresh)
        except TokenError:
            return Response({'detail': 'Token inválido o expirado.'}, status=status.HTTP_401_UNAUTHORIZED)

        respuesta = Response({'detail': 'Token renovado.'})
        _asignar_cookies_auth(respuesta, access_token, new_refresh_token)
        return respuesta


@extend_schema(
    tags=['Autenticación'],
    summary='Perfil del usuario autenticado',
    description='Retorna los datos del usuario que realiza la petición.',
    responses={200: SegUsuarioMeSerializer},
)
class MeView(APIView):
    def get(self, request):
        return Response(SegUsuarioMeSerializer(request.user).data)


@extend_schema(
    tags=['Autenticación'],
    summary='Cerrar sesión',
    description='Blacklistea el refresh token y limpia las cookies de autenticación.',
    request=_SolicitudRefresco,
    responses={200: _RespuestaDetalle},
)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.COOKIES.get('refresh_token') or request.data.get('refresh')
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass

        respuesta = Response({'detail': 'Logout exitoso.'})
        dominio = settings.AUTH_COOKIE_DOMAIN
        respuesta.delete_cookie('access_token', domain=dominio)
        respuesta.delete_cookie('refresh_token', domain=dominio)
        return respuesta
