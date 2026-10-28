"""
Juego de imagen pública: un original y una miniatura cuadrada, en WebP, en
`B2_BUCKET_PUBLICO`. Es el núcleo común de la foto de perfil (`seguridad.foto`) y
de la imagen del contenedor (`contenedor.imagen`); cada uno pone su `prefijo` y
guarda el uuid en su fila.

Layout en B2:
    <prefijo>/<uuid>/original.webp
    <prefijo>/<uuid>/thumb.webp

El `uuid` cambia en cada subida y eso es deliberado, por dos motivos:

- **La URL anterior deja de servir.** Con una ruta fija (`foto.jpg`) el navegador
  y cualquier CDN siguen mostrando la imagen vieja después de cambiarla, porque
  la URL no cambió. Acá cada subida estrena URL, así que se puede cachear para
  siempre sin miedo.
- **No se puede enumerar.** `<prefijo>/foto.jpg` es adivinable con solo iterar el
  id del prefijo; con el uuid de por medio, no.

Quien sube un juego nuevo borra después el anterior (`borrar`), que ya no lo
referencia nadie.
"""

import logging
import uuid as uuid_lib

from django.conf import settings

from utilidades import backblaze
from utilidades.imagenes import (
    CALIDAD_ORIGINAL,
    CALIDAD_THUMBNAIL,
    LADO_MAXIMO_ORIGINAL,
    LADO_THUMBNAIL,
    a_bytes_webp,
    abrir_imagen,
    recortar_cuadrado,
    redimensionar,
    validar_archivo_imagen,
)

logger = logging.getLogger(__name__)

TIPO = 'image/webp'


def key_original(prefijo: str, imagen_uuid) -> str:
    return f'{prefijo}/{imagen_uuid}/original.webp'


def key_thumbnail(prefijo: str, imagen_uuid) -> str:
    return f'{prefijo}/{imagen_uuid}/thumb.webp'


def url_publica(key: str) -> str | None:
    if not settings.B2_CDN_URL_PUBLICO:
        return None
    return f'{settings.B2_CDN_URL_PUBLICO.rstrip("/")}/{key}'


def subir(archivo, prefijo: str):
    """
    Procesa y sube un juego nuevo bajo `prefijo`. Devuelve su uuid.

    No toca ninguna fila ni borra el juego anterior: eso es de quien llama.
    Lanza ValueError si la imagen no sirve y ErrorDeAlmacenamiento si B2 falla.
    """
    validar_archivo_imagen(archivo)
    imagen = abrir_imagen(archivo)

    # Los dos derivados se arman en memoria antes de subir nada: si el segundo
    # fallara a mitad de camino, quedaría imagen nueva con miniatura vieja, que es
    # la inconsistencia más visible que hay.
    original = a_bytes_webp(redimensionar(imagen.copy(), LADO_MAXIMO_ORIGINAL), CALIDAD_ORIGINAL)
    thumbnail = a_bytes_webp(recortar_cuadrado(imagen.copy(), LADO_THUMBNAIL), CALIDAD_THUMBNAIL)

    nuevo = uuid_lib.uuid4()
    bucket = settings.B2_BUCKET_PUBLICO

    backblaze.subir(bucket, key_original(prefijo, nuevo), original, TIPO)
    try:
        backblaze.subir(bucket, key_thumbnail(prefijo, nuevo), thumbnail, TIPO)
    except Exception:
        borrar(prefijo, nuevo)
        raise
    return nuevo


def borrar(prefijo: str, imagen_uuid) -> None:
    """
    Borra un par original/thumbnail sin dejar que un fallo corte el flujo.

    Que no se pueda borrar la imagen vieja no es motivo para rechazar la nueva:
    queda un objeto huérfano y se registra, nada más.
    """
    bucket = settings.B2_BUCKET_PUBLICO
    for key in (key_original(prefijo, imagen_uuid), key_thumbnail(prefijo, imagen_uuid)):
        try:
            backblaze.eliminar(bucket, key)
        except Exception:  # noqa: BLE001 — borrar en B2 nunca corta el flujo
            logger.warning('No se pudo borrar la imagen en B2: %s', key)
