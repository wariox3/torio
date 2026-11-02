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
        descripcion: str,
        cliente: str | None = None,
        modulo: str | None = None,
        archivos: list | None = None,
        usuario_integracion: int | None = None,
    ):
        """
        Crea un caso. `POST /api/soporte/caso/nuevo`, en multipart para poder
        adjuntar archivos.

        Carbono exige `cliente` (texto libre) y `modulo` (un id de
        `GET /api/soporte/modulo/lista`, p. ej. `GEN`). Son opcionales acá solo por
        si carbono deja de exigirlos: si faltan, responde 400.

        `archivos` es una lista de tuplas `(nombre, contenido, mime)`, con el
        contenido en bytes o como archivo abierto; carbono admite máximo 5 de 10 MB
        cada uno. Si sale bien, `datos` trae `id` (el número del caso) y
        `adjuntosFallidos`, un **número**: el caso se crea aunque algún adjunto no
        se pueda guardar.

        `usuario_integracion` es el id del usuario en torio (carbono lo lee como
        `usuarioIntegracion`); con él y el correo se listan después sus casos.
        """
        datos = {
            'tipo': tipo,
            'contacto': contacto,
            'correo': correo,
            'telefono': telefono,
            'descripcion': descripcion,
        }
        if cliente:
            datos['cliente'] = cliente
        if modulo:
            datos['modulo'] = modulo
        if usuario_integracion is not None:
            datos['usuarioIntegracion'] = usuario_integracion
        adjuntos = [('files[]', archivo) for archivo in archivos or []]
        respuesta = self._enviar(
            'POST', '/api/soporte/caso/nuevo', data=datos, files=adjuntos or None,
            # Holgado porque puede llevar hasta 50 MB de adjuntos.
            timeout=60,
        )
        return {'error': respuesta['status'] != 200, **respuesta}

    def caso_lista_usuario_integracion(self, usuario_integracion: int, correo: str):
        """
        Los 3 últimos casos de un usuario. `GET /api/soporte/caso/lista-usuario-integracion`.

        Carbono filtra por `usuarioIntegracion` **y** `correo` (exacto), para que
        nadie lea casos ajenos adivinando el id. Si sale bien, `datos` trae
        `casos`: lista de `{id, descripcion, estadoAtendido, estadoRespuesta,
        estadoCerrado}`, del más nuevo al más viejo.
        """
        respuesta = self._enviar(
            'GET', '/api/soporte/caso/lista-usuario-integracion',
            params={'usuarioIntegracion': usuario_integracion, 'correo': correo},
            timeout=15,
        )
        return {'error': respuesta['status'] != 200, **respuesta}

    def _enviar(self, metodo: str, url: str, **kwargs):
        if not settings.CARBONO_KEY:
            logger.error('Carbono: falta CARBONO_KEY')
            return {'status': 500, 'datos': {'mensaje': 'La mesa de ayuda no está configurada.'}}
        try:
            respuesta = httpx.request(
                metodo,
                settings.CARBONO_URL + url,
                headers={'Authorization': f'Bearer {settings.CARBONO_KEY}'},
                **kwargs,
            )
            return {'status': respuesta.status_code, 'datos': respuesta.json()}
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as e:
            logger.error('Carbono error: %s', e)
            return {'status': 500, 'datos': {'mensaje': 'No fue posible comunicarse con la mesa de ayuda.'}}
