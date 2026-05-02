import logging

import httpx
from django.conf import settings
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def verify_turnstile(token: str, ip: str = None):
    if not settings.TURNSTILE_ENABLED:
        return

    if not token:
        raise ValidationError({'turnstile_token': 'Token de Turnstile requerido.'})

    data = {'secret': settings.TURNSTILE_SECRET_KEY, 'response': token}
    if ip:
        data['remoteip'] = ip

    try:
        respuesta = httpx.post(_VERIFY_URL, data=data, timeout=5)
        resultado = respuesta.json()
    except Exception as e:
        logger.error('Error al verificar Turnstile: %s', e)
        raise ValidationError({'turnstile_token': 'No se pudo verificar el token. Intenta de nuevo.'})

    if not resultado.get('success'):
        codes = resultado.get('error-codes', [])
        logger.warning('Turnstile rechazado: %s', codes)
        raise ValidationError({'turnstile_token': 'Verificación de Turnstile fallida.'})
