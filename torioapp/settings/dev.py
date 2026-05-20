from datetime import timedelta

from .base import *  # noqa: F401,F403

DEBUG = True

ENABLE_API_DOCS = True
AUTH_COOKIE_DOMAIN = None

SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'] = timedelta(hours=12)
SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'] = timedelta(days=30)

CORS_ALLOWED_ORIGINS = [
    'http://localhost:4200',
]
