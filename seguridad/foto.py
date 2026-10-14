"""
Foto de perfil: la imagen de la cuenta, sobre el juego de `utilidades.imagen_publica`.

La foto es de la cuenta, no del contenedor: vive en el schema público, igual que
`SegUsuario`. Nada de acá toca un tenant.

Layout en B2 (`B2_BUCKET_PUBLICO`):
    usuarios/<user_id>/<uuid>/original.webp
    usuarios/<user_id>/<uuid>/thumb.webp
"""

from utilidades import imagen_publica
from utilidades.imagen_publica import url_publica  # noqa: F401  (lo usa el serializer)


def _prefijo(user_id: int) -> str:
    return f'usuarios/{user_id}'


def key_original(user_id: int, imagen_uuid) -> str:
    return imagen_publica.key_original(_prefijo(user_id), imagen_uuid)


def key_thumbnail(user_id: int, imagen_uuid) -> str:
    return imagen_publica.key_thumbnail(_prefijo(user_id), imagen_uuid)


def subir_foto(archivo, usuario):
    """
    Procesa y sube la foto de `usuario`. Devuelve el uuid del juego nuevo.

    Lanza ValueError si la imagen no sirve y ErrorDeAlmacenamiento si B2 falla.
    """
    anterior = usuario.imagen_uuid
    nuevo = imagen_publica.subir(archivo, _prefijo(usuario.id))

    usuario.imagen_uuid = nuevo
    usuario.save(update_fields=['imagen_uuid'])

    if anterior:
        imagen_publica.borrar(_prefijo(usuario.id), anterior)
    return nuevo
