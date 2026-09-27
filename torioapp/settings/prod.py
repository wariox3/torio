from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

# Redis es un servicio gestionado, así que acá `REDIS_URL` es obligatoria: con el
# `localhost` por defecto de base.py la app arrancaría contra un Redis que no existe
# y, como el cache falla abierto, el throttling quedaría sin límite sin que nada
# avise. Y va por TLS (`rediss://`): el servicio está en internet. redis-py ya
# verifica el certificado y el nombre del host por defecto.
REDIS_URL = config('REDIS_URL')
if not REDIS_URL.startswith('rediss://'):
    raise ImproperlyConfigured('REDIS_URL tiene que ser rediss:// (TLS) en producción.')
CACHES['default']['LOCATION'] = REDIS_URL  # noqa: F405

# HTTPS / cookies
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Otros
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
