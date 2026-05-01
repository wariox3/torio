from .base import *  # noqa: F401,F403

# Sobreescritos seguros para desarrollo local.
DEBUG = True

# CORS_ALLOW_ALL_ORIGINS no es compatible con CORS_ALLOW_CREDENTIALS.
# Especificamos el origen del frontend Angular en desarrollo.
CORS_ALLOWED_ORIGINS = [
    'http://localhost:4200',
]

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
