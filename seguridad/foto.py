"""
Foto de perfil: procesamiento, almacenamiento y borrado del juego anterior.

La foto es de la cuenta, no del contenedor: vive en el schema público, igual que
`SegUsuario`. Nada de acá toca un tenant.

Layout en B2 (`B2_BUCKET_PUBLICO`):
    usuarios/<user_id>/<uuid>/original.webp
    usuarios/<user_id>/<uuid>/thumb.webp

El `uuid` cambia en cada subida y eso es deliberado, por dos motivos:

- **La URL anterior deja de servir.** Con una ruta fija (`foto.jpg`) el navegador
  y cualquier CDN siguen mostrando la imagen vieja después de cambiarla, porque
  la URL no cambió. Acá cada subida estrena URL, así que se puede cachear para
  siempre sin miedo.
- **No se puede enumerar.** `usuarios/<id>/foto.jpg` es adivinable con solo
  iterar el id; con el uuid de por medio, no.

Tras subir el juego nuevo se borra el anterior, que ya no lo referencia nadie.
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


def key_original(user_id: int, imagen_uuid) -> str:
    return f'usuarios/{user_id}/{imagen_uuid}/original.webp'


def key_thumbnail(user_id: int, imagen_uuid) -> str:
    return f'usuarios/{user_id}/{imagen_uuid}/thumb.webp'


def url_publica(key: str) -> str | None:
    if not settings.B2_CDN_URL_PUBLICO:
        return None
    return f'{settings.B2_CDN_URL_PUBLICO.rstrip("/")}/{key}'


def subir_foto(archivo, usuario):
    """
    Procesa y sube la foto de `usuario`. Devuelve el uuid del juego nuevo.

    Lanza ValueError si la imagen no sirve y ErrorDeAlmacenamiento si B2 falla.
    """
    validar_archivo_imagen(archivo)
    imagen = abrir_imagen(archivo)

    # Los dos derivados se arman en memoria antes de subir nada: si el segundo
    # fallara a mitad de camino, el usuario quedaría con foto nueva y miniatura
    # vieja, que es la inconsistencia más visible que hay.
    original = a_bytes_webp(redimensionar(imagen.copy(), LADO_MAXIMO_ORIGINAL), CALIDAD_ORIGINAL)
    thumbnail = a_bytes_webp(recortar_cuadrado(imagen.copy(), LADO_THUMBNAIL), CALIDAD_THUMBNAIL)

    anterior = usuario.imagen_uuid
    nuevo = uuid_lib.uuid4()
    bucket = settings.B2_BUCKET_PUBLICO

    backblaze.subir(bucket, key_original(usuario.id, nuevo), original, TIPO)
    try:
        backblaze.subir(bucket, key_thumbnail(usuario.id, nuevo), thumbnail, TIPO)
    except Exception:
        _borrar_juego(usuario.id, nuevo)
        raise

    usuario.imagen_uuid = nuevo
    usuario.save(update_fields=['imagen_uuid'])

    if anterior:
        _borrar_juego(usuario.id, anterior)
    return nuevo


def _borrar_juego(user_id: int, imagen_uuid) -> None:
    """
    Borra un par original/thumbnail sin dejar que un fallo corte el flujo.

    Que no se pueda borrar la foto vieja no es motivo para rechazar la nueva:
    queda un objeto huérfano y se registra, nada más.
    """
    bucket = settings.B2_BUCKET_PUBLICO
    for key in (key_original(user_id, imagen_uuid), key_thumbnail(user_id, imagen_uuid)):
        try:
            backblaze.eliminar(bucket, key)
        except Exception:
            logger.warning('No se pudo borrar la foto anterior en B2: %s', key)
