import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# Tipos de caso que acepta carbono (`CasoTipo`).
TIPOS_CASO = ('SOP', 'ERR', 'CES', 'DES', 'SOL', 'SER')


class Carbono:
    """
    Cliente de la mesa de ayuda carbono (`CARBONO_URL`).

    Se autentica con `Authorization: Bearer <CARBONO_KEY>`, un token que se crea
    en carbono con `app:api-token`. Los errores de carbono llegan como
    `{"mensaje": ...}`.
    """

    def caso_nuevo(
        self,
        tipo: str,
        contacto: str,
        correo: str,
        telefono: str,
        cliente: str,
        modulo: str,
        descripcion: str,
        archivos: list | None = None,
    ):
        """
        Crea un caso. `POST /api/soporte/caso/nuevo`, en multipart para poder
        adjuntar archivos.

        `archivos` es una lista de tuplas `(nombre, contenido, mime)`; carbono
        admite máximo 5 de 10 MB cada uno. Si sale bien, `datos` trae `id` (el
        número del caso) y `adjuntosFallidos`: el caso se crea aunque algún
        adjunto no se pueda guardar.
        """
        datos = {
            'tipo': tipo,
            'contacto': contacto,
            'correo': correo,
            'telefono': telefono,
            'cliente': cliente,
            'modulo': modulo,
            'descripcion': descripcion,
        }
        adjuntos = [('files[]', archivo) for archivo in archivos or []]
        respuesta = self._post('/api/soporte/caso/nuevo', datos, adjuntos)
        return {'error': respuesta['status'] != 200, **respuesta}

    def _post(self, url: str, datos: dict, archivos: list):
        if not settings.CARBONO_KEY:
            logger.error('Carbono: falta CARBONO_KEY')
            return {'status': 500, 'datos': {'mensaje': 'La mesa de ayuda no está configurada.'}}
        try:
            respuesta = httpx.post(
                settings.CARBONO_URL + url,
                data=datos,
                files=archivos or None,
                headers={'Authorization': f'Bearer {settings.CARBONO_KEY}'},
                # Holgado porque puede llevar hasta 50 MB de adjuntos.
                timeout=60,
            )
            return {'status': respuesta.status_code, 'datos': respuesta.json()}
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as e:
            logger.error('Carbono error: %s', e)
            return {'status': 500, 'datos': {'mensaje': 'No fue posible comunicarse con la mesa de ayuda.'}}
