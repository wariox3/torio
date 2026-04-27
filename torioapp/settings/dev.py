from .base import *  # noqa: F401,F403

# Sobreescritos seguros para desarrollo local.
DEBUG = True

# CORS abierto en dev — en prod se restringe vía env.
CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
