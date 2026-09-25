"""
Cliente del servicio RedEDoc (`api.rededoc.uk`, internamente "nobelio").

Un solo lugar para hablar con ese API: acá viven la URL base, el token y el
manejo de errores de red, y cada endpoint se agrega como un método de la clase.
Las credenciales salen de `settings.REDEDOC_URL` y `settings.REDEDOC_KEY`
(esta última se lee de la variable de entorno `REDEDOC_KEY`).

Todos los métodos públicos devuelven la misma forma de respuesta, igual que
`utilidades.zinc.Zinc`, para que quien llame no tenga que atrapar excepciones:

    {'error': bool, 'status': int, 'datos': dict}

`error=True` con `status=0` significa que la petición ni siquiera salió
(timeout, DNS, conexión rechazada).
"""

import hashlib
import hmac
import logging
import time

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

    def crear_documento(self, datos: dict):
        """
        Crea un documento electrónico (factura, nota…) del emisor.
        `POST /api/documentos/documento/`. Crearlo reserva el consecutivo en
        rededoc; firmarlo y enviarlo a la DIAN es un paso aparte.
        """
        return self._peticion('POST', '/api/documentos/documento/', datos=datos)

    # Notificar incluye el envío del correo por la pasarela, dentro de la misma
    # llamada: con el timeout general se cortaba antes de que rededoc respondiera.
    TIMEOUT_NOTIFICAR = 30

    def notificar_documento(self, documento_id, pdf: bytes, nombre: str, correo: str):
        """
        Le entrega el documento al adquiriente.
        `POST /api/documentos/documento/{id}/notificar/`, en multipart con `pdf` y
        `correo`, la dirección a la que se envía.

        Rededoc arma el zip —el AttachedDocument con el acuse de la DIAN más la
        representación gráfica—, lo envía por correo y marca el documento como
        notificado. Solo acepta documentos que la DIAN ya validó.
        """
        return self._peticion(
            'POST', f'/api/documentos/documento/{documento_id}/notificar/',
            datos={'correo': correo},
            archivos={'pdf': (nombre, pdf, 'application/pdf')},
            timeout=self.TIMEOUT_NOTIFICAR,
        )

    # --- Interno -----------------------------------------------------------

    def _headers(self):
        headers = {'Accept': 'application/json'}
        if self.key:
            headers['Authorization'] = f'{self.ESQUEMA_AUTH} {self.key}'
        else:
            logger.warning('RedEDoc sin llave configurada (REDEDOC_KEY vacía)')
        return headers

    def _peticion(self, metodo: str, ruta: str, datos: dict = None, parametros: dict = None,
                  archivos: dict = None, timeout: float = None):
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
                timeout=timeout or self.timeout,
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


# --- Firma de los avisos del webhook -------------------------------------
#
# Rededoc firma cada aviso que le manda a torio:
#
#     X-Rededoc-Fecha: <timestamp unix, en segundos>
#     X-Rededoc-Firma: v1=<hex de HMAC-SHA256(secreto, "<fecha>.<cuerpo crudo>")>
#
# La fecha entra en lo firmado para que un aviso capturado no se pueda reenviar
# después de `TOLERANCIA_FIRMA`. El cuerpo es el crudo, tal cual llegó: firmar el
# JSON ya parseado dependería de cómo cada lado lo serializa.

HEADER_FECHA = 'X-Rededoc-Fecha'
HEADER_FIRMA = 'X-Rededoc-Firma'
VERSION_FIRMA = 'v1'
TOLERANCIA_FIRMA = 300  # segundos, hacia atrás y hacia adelante


def firmar_aviso(cuerpo: bytes, fecha: str, secreto: str) -> str:
    """El valor de `X-Rededoc-Firma` para ese cuerpo y esa fecha."""
    mensaje = fecha.encode() + b'.' + cuerpo
    digest = hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()
    return f'{VERSION_FIRMA}={digest}'


def firma_valida(cuerpo: bytes, fecha: str, firma: str, ahora: float = None) -> bool:
    """
    ¿Viene el aviso de rededoc y es reciente?

    Se acepta con el secreto actual o con el anterior, para poder rotarlo sin
    rechazar los avisos que ya iban en camino. Sin ningún secreto configurado se
    rechaza todo: un webhook que acepta avisos sin verificar deja que cualquiera
    marque facturas como validadas.
    """
    secretos = [s for s in (settings.REDEDOC_WEBHOOK_SECRETO,
                            settings.REDEDOC_WEBHOOK_SECRETO_ANTERIOR) if s]
    if not secretos:
        logger.error('Aviso de rededoc rechazado: REDEDOC_WEBHOOK_SECRETO no está configurado')
        return False
    if not fecha or not firma:
        return False
    try:
        marca = int(fecha)
    except ValueError:
        return False
    ahora = time.time() if ahora is None else ahora
    if abs(ahora - marca) > TOLERANCIA_FIRMA:
        return False
    # `compare_digest` en todos los casos, para que el tiempo de respuesta no
    # diga cuánto de la firma coincidía.
    return any(
        hmac.compare_digest(firmar_aviso(cuerpo, fecha, secreto), firma)
        for secreto in secretos
    )
