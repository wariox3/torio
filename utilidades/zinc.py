import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class Zinc:

    def correo(self, correo: str, asunto: str, contenido: str, aplicacion='reddoc', archivos: list = []):
        datos = {
            'correo': correo,
            'asunto': asunto,
            'contenido': contenido,
            'aplicacion': aplicacion,
            'archivos': archivos,
        }
        respuesta = self._post(datos, '/api/correo/itrio')
        if respuesta['status'] == 200:
            return {'error': False, 'status': respuesta['status'], 'datos': respuesta['datos']}
        return {'error': True, 'status': respuesta['status'], 'datos': respuesta['datos']}

    def _post(self, data: dict, url: str):
        full_url = settings.ZINC_URL + url
        try:
            response = httpx.post(full_url, json=data, timeout=10)
            return {'status': response.status_code, 'datos': response.json()}
        except Exception as e:
            logger.error('Zinc error: %s', e)
            return {'status': 500, 'datos': {}}
