"""
Imágenes de un registro: procesamiento, subida a B2 y persistencia en GenImagen.

A diferencia de un adjunto (`general/servicios/archivo.py`), la imagen no se
guarda como llega: se convierte a WebP y se sube en dos tamaños. Y vive en
`B2_BUCKET_PUBLICO`, porque el front la carga directo por URL — una lista de
ítems con miniaturas no puede ser una petición al back por fila.

Layout en B2:
    <cliente_pk>/imagenes/<uuid>/original.webp
    <cliente_pk>/imagenes/<uuid>/thumb.webp

El `uuid` es lo único que protege la URL: el bucket es público, así que quien
tenga el enlace ve la imagen sin sesión. No es adivinable, pero tampoco es un
control de acceso.

Un registro puede tener varias imágenes y exactamente una es la principal (la
que se muestra en las listas) mientras tenga alguna.
"""

import logging
import uuid as uuid_lib

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import CharField, OuterRef, Subquery
from django.db.models.functions import Cast

from general.servicios.archivo import validar_objeto
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
MAX_IMAGENES_POR_REGISTRO = 10


def key_original(imagen_uuid) -> str:
    return f'{connection.tenant.pk}/imagenes/{imagen_uuid}/original.webp'


def key_miniatura(imagen_uuid) -> str:
    return f'{connection.tenant.pk}/imagenes/{imagen_uuid}/thumb.webp'


def _url_publica(key: str) -> str | None:
    if not settings.B2_CDN_URL_PUBLICO:
        return None
    return f'{settings.B2_CDN_URL_PUBLICO.rstrip("/")}/{key}'


def url_original(imagen_uuid) -> str | None:
    return _url_publica(key_original(imagen_uuid)) if imagen_uuid else None


def url_miniatura(imagen_uuid) -> str | None:
    return _url_publica(key_miniatura(imagen_uuid)) if imagen_uuid else None


def subir_imagen(archivo, modelo, objeto_id):
    """
    Procesa, sube a B2 y crea un GenImagen. Retorna la instancia creada.

    La primera imagen de un registro queda como principal. Lanza ValueError si
    la imagen o el registro no sirven y ErrorDeAlmacenamiento si B2 falla.
    """
    from general.models import GenImagen

    validar_archivo_imagen(archivo)
    validar_objeto(modelo, objeto_id)

    existentes = GenImagen.objects.filter(modelo=modelo, objeto_id=str(objeto_id))
    if existentes.count() >= MAX_IMAGENES_POR_REGISTRO:
        raise ValueError(f'El registro ya tiene el máximo de {MAX_IMAGENES_POR_REGISTRO} imágenes.')

    imagen = abrir_imagen(archivo)
    # Los dos derivados se arman en memoria antes de subir nada, igual que en
    # la foto de perfil: una imagen sin miniatura es un hueco en cada lista.
    original = a_bytes_webp(redimensionar(imagen.copy(), LADO_MAXIMO_ORIGINAL), CALIDAD_ORIGINAL)
    miniatura = a_bytes_webp(recortar_cuadrado(imagen.copy(), LADO_THUMBNAIL), CALIDAD_THUMBNAIL)

    nuevo_uuid = uuid_lib.uuid4()
    bucket = settings.B2_BUCKET_PUBLICO

    backblaze.subir(bucket, key_original(nuevo_uuid), original, TIPO)
    try:
        backblaze.subir(bucket, key_miniatura(nuevo_uuid), miniatura, TIPO)
        return _crear_fila(modelo, objeto_id, nuevo_uuid, principal=not existentes.exists())
    except Exception:
        # Los objetos ya están en B2 pero no habrá fila que los referencie.
        _borrar_juego(nuevo_uuid)
        raise


def _crear_fila(modelo, objeto_id, imagen_uuid, principal):
    from general.models import GenImagen

    datos = {'modelo': modelo, 'objeto_id': str(objeto_id), 'uuid': imagen_uuid}
    if not principal:
        return GenImagen.objects.create(**datos)
    try:
        # El savepoint deja la transacción usable si la restricción salta.
        with transaction.atomic():
            return GenImagen.objects.create(principal=True, **datos)
    except IntegrityError:
        # Otra subida al mismo registro ganó la carrera y ya es la principal.
        return GenImagen.objects.create(**datos)


@transaction.atomic
def marcar_principal(imagen) -> None:
    """Deja `imagen` como la única principal de su registro."""
    from general.models import GenImagen

    # Primero se quita la anterior: la restricción no admite dos a la vez.
    GenImagen.objects.filter(
        modelo_id=imagen.modelo_id, objeto_id=imagen.objeto_id, principal=True,
    ).exclude(pk=imagen.pk).update(principal=False)
    imagen.principal = True
    imagen.save(update_fields=['principal'])


def eliminar_imagen(imagen) -> None:
    """
    Elimina los objetos en B2 y la fila. Si era la principal, pasa a serlo la
    más reciente que quede.
    """
    from general.models import GenImagen

    bucket = settings.B2_BUCKET_PUBLICO
    backblaze.eliminar(bucket, key_original(imagen.uuid))
    backblaze.eliminar(bucket, key_miniatura(imagen.uuid))

    with transaction.atomic():
        era_principal = imagen.principal
        modelo_id, objeto_id = imagen.modelo_id, imagen.objeto_id
        imagen.delete()
        if era_principal:
            siguiente = GenImagen.objects.filter(
                modelo_id=modelo_id, objeto_id=objeto_id,
            ).order_by('-id').first()
            if siguiente:
                siguiente.principal = True
                siguiente.save(update_fields=['principal'])


def eliminar_imagenes_de(clase, objeto_id) -> None:
    """
    Borra todas las imágenes de un registro que ya se eliminó.

    Recibe la clase y el id, no la instancia: tras `delete()` la instancia ya
    no tiene pk. Un fallo de B2 no se propaga — el registro ya no existe y no
    hay a quién devolverle el error; queda el objeto huérfano y se registra.
    """
    from general.models import GenImagen

    imagenes = GenImagen.objects.filter(
        modelo__app=clase._meta.app_label, modelo__clase=clase.__name__, objeto_id=str(objeto_id),
    )
    for imagen_uuid in list(imagenes.values_list('uuid', flat=True)):
        _borrar_juego(imagen_uuid)
    imagenes.delete()


def _borrar_juego(imagen_uuid) -> None:
    """Borra el par original/miniatura sin dejar que un fallo corte el flujo."""
    bucket = settings.B2_BUCKET_PUBLICO
    for key in (key_original(imagen_uuid), key_miniatura(imagen_uuid)):
        try:
            backblaze.eliminar(bucket, key)
        except Exception:  # noqa: BLE001 — borrar en B2 nunca corta el flujo
            logger.warning('No se pudo borrar la imagen en B2: %s', key)


def anotar_imagen_principal(qs):
    """
    Agrega `imagen_principal_uuid` a cada fila de `qs`.

    Es lo que evita una consulta por fila en las listas: la principal sale en
    la misma consulta, como subconsulta.
    """
    from general.models import GenImagen

    clase = qs.model
    principal = GenImagen.objects.filter(
        modelo__app=clase._meta.app_label,
        modelo__clase=clase.__name__,
        objeto_id=Cast(OuterRef('pk'), CharField()),
        principal=True,
    ).values('uuid')[:1]
    return qs.annotate(imagen_principal_uuid=Subquery(principal))


def uuid_principal(instancia):
    """
    El uuid de la imagen principal de `instancia`, o None.

    Usa la anotación de `anotar_imagen_principal` si la fila la trae y consulta
    solo cuando no (una instancia recién creada, que no salió de ese queryset).
    """
    from general.models import GenImagen

    if not hasattr(instancia, 'imagen_principal_uuid'):
        clase = type(instancia)
        instancia.imagen_principal_uuid = GenImagen.objects.filter(
            modelo__app=clase._meta.app_label,
            modelo__clase=clase.__name__,
            objeto_id=str(instancia.pk),
            principal=True,
        ).values_list('uuid', flat=True).first()
    return instancia.imagen_principal_uuid
