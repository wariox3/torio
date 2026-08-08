from datetime import timedelta

from .base import *  # noqa: F401,F403

DEBUG = True

TURNSTILE_ENABLED = False
ENABLE_API_DOCS = True
AUTH_COOKIE_DOMAIN = None

# Access de 1 hora, no de 12: con 12 h no se alcanza a ver el efecto de blacklistear
# sesiones (activar/desactivar MFA, logout), porque el token viejo sigue sirviendo medio
# día y parece un bug. El refresh largo mantiene la comodidad de no re-loguearse.
SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'] = timedelta(hours=1)
SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'] = timedelta(days=30)

CORS_ALLOWED_ORIGINS = [
    'http://localhost:4200',
]
