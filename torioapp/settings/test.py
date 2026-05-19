from .base import *  # noqa: F401,F403

DEBUG = False

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

TURNSTILE_ENABLED = True
TURNSTILE_SECRET_KEY = '1x0000000000000000000000000000000AA'
ENABLE_API_DOCS = True

CORS_ALLOWED_ORIGINS = [
    'https://reddoc.uk',
    'https://www.reddoc.uk',
]
