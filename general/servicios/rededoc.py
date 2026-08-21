"""
Cliente del servicio RedEDoc (`api.rededoc.uk`, internamente "nobelio").

Un solo lugar para hablar con ese API: acá viven la URL base, el token y el
manejo de errores de red, y cada endpoint se agrega como un método de la clase.
Las credenciales salen de `settings.REDEDOC_URL` y `settings.REDEDOC_KEY`
(esta última se lee de la variable de entorno `KEY_REDEDOC`).

Todos los métodos públicos devuelven la misma forma de respuesta, igual que
`utilidades.zinc.Zinc`, para que quien llame no tenga que atrapar excepciones:

    {'error': bool, 'status': int, 'datos': dict}

`error=True` con `status=0` significa que la petición ni siquiera salió
(timeout, DNS, conexión rechazada).
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class Rededoc:

    # El API autentica por token en el header Authorization. El esquema va acá y
    # no repetido en cada método: si el servicio cambia de prefijo, se toca una línea.
    ESQUEMA_AUTH = 'Api-Key'
    TIMEOUT = 10

    def __init__(self, url: str = None, key: str = None, timeout: float = None):
        self.url = (url or settings.REDEDOC_URL).rstrip('/')
        self.key = key if key is not None else settings.REDEDOC_KEY
        self.timeout = timeout or self.TIMEOUT

    # --- Endpoints ---------------------------------------------------------

    def estado(self):
        """
        Prueba de vida del servicio. `GET /estado/` responde
        `{'servicio': 'nobelio', 'estado': 'ok'}`.
        """
        return self._peticion('GET', '/estado/')

    # --- Interno -----------------------------------------------------------

    def _headers(self):
        headers = {'Accept': 'application/json'}
        if self.key:
            headers['Authorization'] = f'{self.ESQUEMA_AUTH} {self.key}'
        else:
            logger.warning('RedEDoc sin llave configurada (KEY_REDEDOC vacía)')
        return headers

    def _peticion(self, metodo: str, ruta: str, datos: dict = None, parametros: dict = None):
        url_completa = self.url + ruta
        try:
            respuesta = httpx.request(
                metodo,
                url_completa,
                json=datos,
                params=parametros,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except Exception as e:
            logger.error('RedEDoc %s %s falló: %s', metodo, url_completa, e)
            return {'error': True, 'status': 0, 'datos': {'mensaje': f'No se pudo contactar el servicio RedEDoc: {e}'}}

        cuerpo = self._cuerpo(respuesta)
        if respuesta.status_code >= 400:
            logger.warning('RedEDoc %s %s HTTP %s: %s', metodo, url_completa, respuesta.status_code, cuerpo)
            return {'error': True, 'status': respuesta.status_code, 'datos': cuerpo}
        return {'error': False, 'status': respuesta.status_code, 'datos': cuerpo}

    @staticmethod
    def _cuerpo(respuesta):
        """El API responde JSON, pero un 502 del proxy o un 404 de Apache llega en HTML."""
        try:
            return respuesta.json()
        except Exception:
            return {'mensaje': respuesta.text[:500]}
