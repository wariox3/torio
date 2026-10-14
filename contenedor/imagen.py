"""
Imagen del contenedor: la que lo identifica en la interfaz (la lista de
contenedores, el encabezado), sobre el juego de `utilidades.imagen_publica`.

Vive en el schema público, en `CtnCliente.imagen_uuid`, porque la lista de
contenedores se arma sin `X-Tenant`: si estuviera dentro del tenant habría que
entrar a cada schema para mostrarla. No es el logotipo de los formatos impresos
(`GenConfiguracion.gen_empresa_logotipo`), que sí es del tenant.

Layout en B2 (`B2_BUCKET_PUBLICO`), bajo el mismo `<cliente_pk>/` que `GenImagen`:
    <cliente_pk>/contenedor/<uuid>/original.webp
    <cliente_pk>/contenedor/<uuid>/thumb.webp
"""

from utilidades import imagen_publica


def _prefijo(cliente_id: int) -> str:
    return f'{cliente_id}/contenedor'


def url_original(cliente) -> str | None:
    if not cliente.imagen_uuid:
        return None
    return imagen_publica.url_publica(
        imagen_publica.key_original(_prefijo(cliente.id), cliente.imagen_uuid),
    )


def url_thumbnail(cliente) -> str | None:
    # Null sin imagen, en vez de una por defecto: el front decide qué mostrar.
    if not cliente.imagen_uuid:
        return None
    return imagen_publica.url_publica(
        imagen_publica.key_thumbnail(_prefijo(cliente.id), cliente.imagen_uuid),
    )


def subir(archivo, cliente):
    """
    Procesa y sube la imagen de `cliente`, y borra la anterior. Devuelve el uuid.

    `update` y no `save`: el `save` de django-tenants crea el schema si no lo
    encuentra, y acá solo se cambia una columna del schema público.

    Lanza ValueError si la imagen no sirve y ErrorDeAlmacenamiento si B2 falla.
    """
    anterior = cliente.imagen_uuid
    nuevo = imagen_publica.subir(archivo, _prefijo(cliente.id))

    type(cliente).objects.filter(pk=cliente.pk).update(imagen_uuid=nuevo)
    cliente.imagen_uuid = nuevo

    if anterior:
        borrar(cliente.id, anterior)
    return nuevo


def quitar(cliente):
    """
    Deja el contenedor sin imagen y borra la que tenía de B2.

    Es idempotente: quitarla a un contenedor que no tiene ninguna no es un error,
    es el estado que se pedía.
    """
    anterior = cliente.imagen_uuid
    if not anterior:
        return
    type(cliente).objects.filter(pk=cliente.pk).update(imagen_uuid=None)
    cliente.imagen_uuid = None
    borrar(cliente.id, anterior)


def borrar(cliente_id: int, imagen_uuid) -> None:
    """Borra de B2 un juego del contenedor; un fallo queda en el log, no corta."""
    imagen_publica.borrar(_prefijo(cliente_id), imagen_uuid)
