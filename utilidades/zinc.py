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

    def sms(
        self,
        numero: str,
        mensaje: str,
        operador: int = 1,
        soporte=None,
        modelo=None,
        codigo_documento=None,
    ) -> bool:
        if not (isinstance(numero, str) and numero.isdigit() and len(numero) == 10):
            logger.warning('Zinc SMS número inválido: %r (debe ser string de 10 dígitos)', numero)
            return False
        datos = {
            'operador': operador,
            'sms': [
                {
                    'numero': numero,
                    'mensaje': mensaje,
                    'soporte': soporte,
                    'modelo': modelo,
                    'codigoDocumento': codigo_documento,
                }
            ],
        }
        respuesta = self._post(datos, '/api/sms/enviar')
        if respuesta['status'] != 200:
            logger.warning('Zinc SMS HTTP %s: %s', respuesta['status'], respuesta['datos'])
            return False
        datos_resp = respuesta['datos']
        if datos_resp.get('error'):
            logger.warning('Zinc SMS rechazado: %s', datos_resp)
            return False
        envio = (datos_resp.get('envio') or [{}])[0]
        if envio.get('error'):
            logger.warning('Zinc SMS provider error: %s', envio)
            return False
        return True

    def _post(self, data: dict, url: str):
        url_completa = settings.ZINC_URL + url
        try:
            respuesta = httpx.post(url_completa, json=data, timeout=10)
            return {'status': respuesta.status_code, 'datos': respuesta.json()}
        except Exception as e:
            logger.error('Zinc error: %s', e)
            return {'status': 500, 'datos': {}}
