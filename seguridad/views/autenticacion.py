from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from seguridad import mfa as servicio_mfa
from seguridad.models import METODO_CORREO
from seguridad.serializers import SegLoginSerializer, SegMfaLoginSerializer, SegUsuarioMeSerializer
from utilidades.turnstile import verify_turnstile

_RespuestaDetalle = inline_serializer(
    name='DetailResponse',
    fields={'detail': serializers.CharField()},
)
_SolicitudRefresco = inline_serializer(
    name='RefreshRequest',
    fields={'refresh': serializers.CharField(required=False)},
)
_SolicitudMfaToken = inline_serializer(
    name='MfaTokenRequest',
    fields={'mfa_token': serializers.CharField()},
)

_TIEMPO_MAXIMO_ACCESO = int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
_TIEMPO_MAXIMO_REFRESCO = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
_ROTAR = settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS', False)
_LISTA_NEGRA = settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION', False)
_SESION_MAXIMA = int(settings.SESION_MAXIMA.total_seconds())
_TIEMPO_MAXIMO_DISPOSITIVO = int(servicio_mfa.DURACION_DISPOSITIVO.total_seconds())

# Claim propio con el instante en que arrancó la sesión. Sobrevive a las rotaciones,
# a diferencia de `iat`, que `set_iat()` reescribe en cada refresco.
_CLAIM_INICIO_SESION = 'ses'

_COOKIE_DISPOSITIVO = 'mfa_dispositivo'


def _asignar_cookies_auth(respuesta, access_token, refresh_token=None):
    seguro = settings.AUTH_COOKIE_SECURE
    dominio = settings.AUTH_COOKIE_DOMAIN
    respuesta.set_cookie('access_token', access_token, max_age=_TIEMPO_MAXIMO_ACCESO,
                         httponly=True, secure=seguro, samesite='Lax', domain=dominio)
    if refresh_token:
        respuesta.set_cookie('refresh_token', refresh_token, max_age=_TIEMPO_MAXIMO_REFRESCO,
                             httponly=True, secure=seguro, samesite='Lax', domain=dominio)


def _emitir_sesion(usuario, request=None, recordar_dispositivo=False):
    """
    Cierra el login: marca el ingreso, emite los JWT y arma la respuesta.

    Único punto donde se emiten cookies de sesión. Si el usuario tiene MFA activo, solo
    se llega acá después de resolver el segundo paso.
    """
    update_last_login(None, usuario)

    refresh = RefreshToken.for_user(usuario)
    refresh[_CLAIM_INICIO_SESION] = int(timezone.now().timestamp())
    access_token = str(refresh.access_token)

    data = SegUsuarioMeSerializer(usuario).data
    if settings.DEBUG:
        data['access_token'] = access_token

    respuesta = Response(data)
    _asignar_cookies_auth(respuesta, access_token, str(refresh))

    if recordar_dispositivo:
        token = servicio_mfa.recordar_dispositivo(
            usuario,
            request.META.get('HTTP_USER_AGENT') if request else None,
            request.META.get('REMOTE_ADDR') if request else None,
        )
        respuesta.set_cookie(
            _COOKIE_DISPOSITIVO, token, max_age=_TIEMPO_MAXIMO_DISPOSITIVO,
            httponly=True, secure=settings.AUTH_COOKIE_SECURE, samesite='Lax',
            domain=settings.AUTH_COOKIE_DOMAIN,
        )

    return respuesta


@extend_schema(
    tags=['Autenticación'],
    summary='Iniciar sesión',
    description=(
        'Valida credenciales y emite JWT en cookies httpOnly + body (para Bearer). '
        'Si la cuenta tiene verificación en dos pasos y el dispositivo no está recordado, '
        'no emite tokens: responde `mfa_requerido` con el `mfa_token` para `/login/mfa/`.'
    ),
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

        # El MFA se evalúa recién acá, con la clave ya validada: así el endpoint no
        # sirve como oráculo de "esta cuenta existe y tiene segundo factor".
        mfa = servicio_mfa.mfa_activo(usuario)
        if mfa and not servicio_mfa.dispositivo_recordado(usuario, request.COOKIES.get(_COOKIE_DISPOSITIVO)):
            desafio, codigo = servicio_mfa.crear_desafio(
                usuario, mfa.metodo, request.META.get('REMOTE_ADDR')
            )
            if mfa.metodo == METODO_CORREO:
                servicio_mfa.enviar_codigo(usuario, codigo)
            return Response({
                'mfa_requerido': True,
                'mfa_token': servicio_mfa.firmar_desafio(desafio),
                'metodo': mfa.metodo,
            })

        return _emitir_sesion(usuario)


@extend_schema(
    tags=['Autenticación'],
    summary='Completar el segundo paso',
    description=(
        'Resuelve el desafío abierto por `/login/`. Acepta el código del método configurado '
        'o un código de respaldo. Con `recordar_dispositivo` deja una cookie de 30 días que '
        'permite saltar este paso en el mismo navegador.'
    ),
    request=SegMfaLoginSerializer,
    responses={
        200: SegUsuarioMeSerializer,
        401: OpenApiResponse(_RespuestaDetalle, description='Código inválido, desafío expirado o bloqueado'),
        429: OpenApiResponse(description='Demasiados intentos (rate limit 10/min)'),
    },
)
class LoginMfaView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'mfa_verificar'

    def post(self, request):
        serializador = SegMfaLoginSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)

        try:
            usuario = servicio_mfa.verificar_desafio(
                serializador.validated_data['mfa_token'],
                serializador.validated_data['codigo'],
            )
        except servicio_mfa.MfaError as e:
            return Response({'detail': str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        return _emitir_sesion(
            usuario,
            request=request,
            recordar_dispositivo=serializador.validated_data['recordar_dispositivo'],
        )


@extend_schema(
    tags=['Autenticación'],
    summary='Reenviar el código del segundo paso',
    description='Solo para el método correo. No reinicia el contador de intentos del desafío.',
    request=_SolicitudMfaToken,
    responses={
        200: _RespuestaDetalle,
        400: OpenApiResponse(_RespuestaDetalle, description='Desafío inválido, expirado o de otro método'),
        429: OpenApiResponse(description='Demasiados reenvíos (rate limit 3/min)'),
    },
)
class LoginMfaReenviarView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'mfa_envio_codigo'

    def post(self, request):
        try:
            servicio_mfa.reenviar_codigo(request.data.get('mfa_token', ''))
        except servicio_mfa.MfaError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Código reenviado.'})


@extend_schema(
    tags=['Autenticación'],
    summary='Renovar access token',
    description=(
        'Renueva el access token. Si rotación está activa, también emite nuevo refresh y '
        'blacklistea el anterior. La sesión caduca de todos modos al alcanzar su duración '
        'máxima, aunque se haya usado sin interrupciones.'
    ),
    request=_SolicitudRefresco,
    responses={
        200: _RespuestaDetalle,
        400: OpenApiResponse(_RespuestaDetalle, description='Refresh token no encontrado'),
        401: OpenApiResponse(_RespuestaDetalle, description='Token inválido, expirado o sesión caducada'),
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

            # Tope absoluto de sesión. Sin esto, `set_exp()` corre el vencimiento en cada
            # rotación y una sesión activa no caduca nunca: un refresh token robado que se
            # rote a diario viviría para siempre, porque el MFA solo se verifica en /login/.
            # `iat` como respaldo cubre los tokens emitidos antes de existir este claim.
            inicio = refresh.payload.get(_CLAIM_INICIO_SESION) or refresh.payload.get('iat')
            if inicio and timezone.now().timestamp() - inicio > _SESION_MAXIMA:
                return Response(
                    {'detail': 'La sesión alcanzó su duración máxima. Inicia sesión de nuevo.'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            access_token = str(refresh.access_token)

            new_refresh_token = None
            if _ROTAR:
                if _LISTA_NEGRA:
                    refresh.blacklist()
                refresh.set_jti()
                refresh.set_exp()
                refresh.set_iat()
                # Se copia el inicio original: la rotación renueva el token, no la sesión.
                refresh[_CLAIM_INICIO_SESION] = inicio
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
        # La cookie de dispositivo sobrevive al logout a propósito: dice "este navegador
        # es de confianza", no "esta sesión está abierta". Se revoca desde el perfil.
        return respuesta
