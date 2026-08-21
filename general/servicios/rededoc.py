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

    def crear_emisor(self, datos: dict):
        """
        Da de alta un emisor. `POST /api/emisores/emisor/`.

        No se manda `cuenta`: rededoc cuelga el emisor de la cuenta de la
        integración que autentica, o sea de nuestra API key. Mandarla sería la
        única forma de colgarlo de la cuenta equivocada.
        """
        return self._peticion('POST', '/api/emisores/emisor/', datos=datos)

    def cargar_certificado(self, emisor_id, archivo, clave: str, nombre: str = 'certificado.p12'):
        """
        Sube el certificado de firma de un emisor.
        `POST /api/emisores/certificado/cargar/`, en multipart con `emisor`, `archivo` y `clave`.

        El archivo viaja como stream: no se lee entero en memoria ni se guarda de
        este lado, porque es la llave privada con la que se firman las facturas.
        """
        return self._peticion(
            'POST', '/api/emisores/certificado/cargar/',
            datos={'emisor': emisor_id, 'clave': clave},
            archivos={'archivo': (nombre, archivo, 'application/x-pkcs12')},
        )

    # --- Interno -----------------------------------------------------------

    def _headers(self):
        headers = {'Accept': 'application/json'}
        if self.key:
            headers['Authorization'] = f'{self.ESQUEMA_AUTH} {self.key}'
        else:
            logger.warning('RedEDoc sin llave configurada (KEY_REDEDOC vacía)')
        return headers

    def _peticion(self, metodo: str, ruta: str, datos: dict = None, parametros: dict = None,
                  archivos: dict = None):
        """
        Con `archivos` la petición sale como multipart y `datos` son los campos del
        formulario; sin ellos, `datos` va como cuerpo JSON. httpx pone el
        `Content-Type` con su boundary, por eso no se fija en `_headers()`.
        """
        url_completa = self.url + ruta
        try:
            respuesta = httpx.request(
                metodo,
                url_completa,
                json=datos if archivos is None else None,
                data=datos if archivos is not None else None,
                files=archivos,
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
