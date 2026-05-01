from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework_simplejwt.authentication import JWTAuthentication


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
        header = self.get_header(request)

        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is None:
                return None
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token

        raw_token = request.COOKIES.get('access_token')
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
