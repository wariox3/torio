"""
Orquestación de archivos: validación, subida a B2 y persistencia en GenArchivo.

Los adjuntos viven en `B2_BUCKET_PRIVADO`: no se sirven directo al navegador,
solo se leen desde el back. `B2_BUCKET_PUBLICO` es para otras funcionalidades
(las fotos de perfil) y no debe usarse acá.

Layout en B2:
    <cliente_pk>/archivos/<modelo_id>/<anio>/<mes>/<uuid>.<ext>

donde `cliente_pk` se toma del tenant actual (connection.tenant.pk) y la fecha
es la de la subida. El nombre real que subió el usuario se guarda en la fila,
no en la ruta: el uuid evita colisiones y no expone nombres.
"""

import logging
import os
import uuid as uuid_lib

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.utils import timezone

from utilidades import backblaze, mime

logger = logging.getLogger(__name__)

TAMANO_MAXIMO_ARCHIVO = 20 * 1024 * 1024  # 20 MB

TIPOS_PERMITIDOS = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/webp',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/msword',
    'application/vnd.ms-excel',
    'text/plain',
    'text/csv',
}


def validar_archivo(archivo) -> str:
    """
    Valida tamaño y tipo, y devuelve el tipo MIME **real** del contenido.

    El `content_type` que manda el cliente no se guarda tal cual: se contrasta
    contra el contenido y se descarta si miente. Deja el puntero del archivo en
    el inicio para que quien siga pueda leerlo.
    """
    if archivo.size > TAMANO_MAXIMO_ARCHIVO:
        raise ValueError(f'El archivo supera el límite de {TAMANO_MAXIMO_ARCHIVO // (1024 * 1024)} MB.')

    declarado = archivo.content_type
    if declarado not in TIPOS_PERMITIDOS:
        raise ValueError(f'Tipo de archivo no permitido: {declarado}')

    archivo.seek(0)
    posibles = mime.tipos_posibles(archivo.read())
    archivo.seek(0)

    if not posibles:
        raise ValueError('El contenido del archivo no corresponde a ningún tipo permitido.')
    if declarado not in posibles:
        raise ValueError(
            f'El contenido del archivo no corresponde a {declarado}.'
        )
    return declarado


def validar_objeto(modelo, objeto_id: str) -> None:
    """
    Lanza ValueError si `objeto_id` no existe en la tabla que describe `modelo`.

    Sin esto se pueden adjuntar archivos a registros que no existen: quedan
    colgando, invisibles para el flujo que debería mostrarlos y sin nada que los
    borre cuando el registro dueño se borra.
    """
    try:
        clase = apps.get_model(modelo.app, modelo.clase)
    except LookupError:
        raise ValueError(f'El modelo {modelo.app}.{modelo.clase} no existe.')

    try:
        existe = clase.objects.filter(pk=objeto_id).exists()
    except (ValueError, TypeError, DjangoValidationError):
        # pk numérica y objeto_id no numérico: no existe y no hay que consultar.
        raise ValueError(f'"{objeto_id}" no es un identificador válido para {modelo.nombre}.')

    if not existe:
        raise ValueError(f'No existe {modelo.nombre} con id {objeto_id}.')


def _extension(nombre: str) -> str:
    _, ext = os.path.splitext(nombre)
    return ext.lower().lstrip('.')


def subir_archivo(archivo, modelo, objeto_id: str, archivo_tipo_id: int = 1):
    """
    Valida, sube a B2 y crea un GenArchivo. Retorna la instancia creada.

    `modelo` es una instancia de GenModelo, no su id: hace falta el par
    app/clase para comprobar que `objeto_id` apunta a un registro real.
    """
    from general.models import GenArchivo

    tipo = validar_archivo(archivo)
    validar_objeto(modelo, objeto_id)

    cliente_pk = connection.tenant.pk
    nuevo_uuid = uuid_lib.uuid4()
    extension = _extension(archivo.name)
    nombre_archivo = f'{nuevo_uuid}.{extension}' if extension else str(nuevo_uuid)
    ahora = timezone.now()
    key = f'{cliente_pk}/archivos/{modelo.pk}/{ahora:%Y}/{ahora:%m}/{nombre_archivo}'

    backblaze.subir(
        bucket=settings.B2_BUCKET_PRIVADO,
        key=key,
        body=archivo.read(),
        content_type=tipo,
    )

    url = f'{settings.B2_CDN_URL_PUBLICO.rstrip("/")}/{key}' if settings.B2_CDN_URL_PUBLICO else None

    try:
        return GenArchivo.objects.create(
            archivo_tipo_id=archivo_tipo_id,
            modelo=modelo,
            objeto_id=str(objeto_id),
            nombre=archivo.name,
            tipo=tipo,
            tamano=archivo.size,
            almacenamiento_id=key,
            uuid=nuevo_uuid,
            url=url,
        )
    except Exception:
        # El objeto ya está en B2 pero no habrá fila que lo referencie: sin esto
        # queda huérfano para siempre, porque nadie sabe que existe.
        try:
            backblaze.eliminar(settings.B2_BUCKET_PRIVADO, key)
        except Exception:
            logger.error('Quedó un objeto huérfano en B2: %s', key)
        raise


def descargar_archivo(gen_archivo) -> bytes:
    """
    Trae el contenido desde B2.

    La verificación de quién puede pedirlo la hace la vista con el queryset del
    contenedor: acá ya se asume que la fila es del tenant actual.
    """
    return backblaze.descargar(settings.B2_BUCKET_PRIVADO, gen_archivo.almacenamiento_id)


def eliminar_archivo(gen_archivo) -> None:
    """Elimina el objeto en B2 y borra el GenArchivo de la DB."""
    backblaze.eliminar(settings.B2_BUCKET_PRIVADO, gen_archivo.almacenamiento_id)
    gen_archivo.delete()
