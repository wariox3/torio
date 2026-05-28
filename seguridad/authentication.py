from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework_simplejwt.authentication import JWTAuthentication

from seguridad.contexto import _usuario_actual


class SegCookieJWTScheme(SimpleJWTScheme):
    target_class = 'seguridad.authentication.SegCookieJWTAuthentication'
    name = ['jwtAuth', 'jwtCookieAuth']

    def get_security_definition(self, auto_schema):
        definitions = super().get_security_definition(auto_schema)
        cookie_def = {
            'type': 'apiKey',
            'in': 'cookie',
            'name': 'access_token',
        }
        if isinstance(definitions, list):
            return definitions + [cookie_def]
        return [definitions, cookie_def]


class SegCookieJWTAuthentication(JWTAuthentication):
    """
    Lee el JWT desde la cookie httpOnly (Angular) o desde el header
    Authorization: Bearer <token> (Postman / clientes externos).
    La protección CSRF la proveen SameSite=Lax en la cookie + CORS restrictivo.
    """

    def authenticate(self, request):
        encabezado = self.get_header(request)

        if encabezado is not None:
            token_sin_procesar = self.get_raw_token(encabezado)
            if token_sin_procesar is None:
                return None
            token_validado = self.get_validated_token(token_sin_procesar)
            usuario = self.get_user(token_validado)
            _usuario_actual.set(usuario)
            return usuario, token_validado

        token_sin_procesar = request.COOKIES.get('access_token')
        if token_sin_procesar is None:
            return None

        try:
            token_validado = self.get_validated_token(token_sin_procesar)
        except Exception:
            return None

        usuario = self.get_user(token_validado)
        _usuario_actual.set(usuario)
        return usuario, token_validado
