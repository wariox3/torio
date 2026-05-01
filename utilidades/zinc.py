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
        url_completa = settings.ZINC_URL + url
        try:
            respuesta = httpx.post(url_completa, json=data, timeout=10)
            return {'status': respuesta.status_code, 'datos': respuesta.json()}
        except Exception as e:
            logger.error('Zinc error: %s', e)
            return {'status': 500, 'datos': {}}
