from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from seguridad.serializers import SegLoginSerializer

_ACCESS_MAX_AGE = int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
_REFRESH_MAX_AGE = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())
_ROTATE = settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS', False)
_BLACKLIST = settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION', False)


def _set_auth_cookies(response, access_token, refresh_token=None):
    secure = not settings.DEBUG
    response.set_cookie('access_token', access_token, max_age=_ACCESS_MAX_AGE,
                        httponly=True, secure=secure, samesite='Lax')
    if refresh_token:
        response.set_cookie('refresh_token', refresh_token, max_age=_REFRESH_MAX_AGE,
                            httponly=True, secure=secure, samesite='Lax')


class SegLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = SegLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data['email'],
            password=serializer.validated_data['password'],
        )
        if user is None:
            return Response({'detail': 'Credenciales inválidas.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_verified:
            return Response(
                {'detail': 'Cuenta no verificada. Revisa tu correo para activarla.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        update_last_login(None, user)
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response({
            'access': access_token,   # para Postman / clientes externos
            'detail': 'Login exitoso.',
        })
        _set_auth_cookies(response, access_token, refresh_token)
        return response


class SegRefreshView(APIView):
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
            if _ROTATE:
                if _BLACKLIST:
                    refresh.blacklist()
                refresh.set_jti()
                refresh.set_exp()
                refresh.set_iat()
                new_refresh_token = str(refresh)
        except TokenError:
            return Response({'detail': 'Token inválido o expirado.'}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({'detail': 'Token renovado.'})
        _set_auth_cookies(response, access_token, new_refresh_token)
        return response


class SegLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.COOKIES.get('refresh_token') or request.data.get('refresh')
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass

        response = Response({'detail': 'Logout exitoso.'})
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        return response
