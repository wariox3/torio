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

    def buscar_emisor(self, numero_identificacion: str):
        """
        Busca un emisor por NIT entre los que alcanza nuestra integración.
        Se usa antes de crear, para que darle dos veces al botón no falle.

        Devuelve la misma forma de siempre; en `datos` va el emisor encontrado
        o `None` si no hay ninguno.
        """
        respuesta = self._peticion(
            'GET', '/api/emisores/emisor/',
            parametros={'numero_identificacion': numero_identificacion},
        )
        if respuesta['error']:
            return respuesta

        resultados = (respuesta['datos'] or {}).get('results') or []
        # El filtro por NIT no está confirmado del lado de rededoc, así que se
        # vuelve a comparar acá: si el parámetro se ignorara, `results` traería
        # emisores ajenos y no queremos darlos por nuestros.
        emisor = next(
            (e for e in resultados if str(e.get('numero_identificacion')) == str(numero_identificacion)),
            None,
        )
        return {'error': False, 'status': respuesta['status'], 'datos': emisor}

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
