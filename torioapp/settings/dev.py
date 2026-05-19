from .base import *  # noqa: F401,F403

DEBUG = True

TURNSTILE_ENABLED = False
ENABLE_API_DOCS = True
AUTH_COOKIE_DOMAIN = '.localhost'

CORS_ALLOWED_ORIGINS = [
    'http://localhost:4200',
]
