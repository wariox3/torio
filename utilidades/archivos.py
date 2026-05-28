"""
Orquestación de archivos: validación, subida a B2 y persistencia en GenArchivo.

Layout en B2:
    archivos/<cliente_pk>/<modelo_id>/<objeto_id>/<uuid>.<ext>

donde `cliente_pk` se toma del tenant actual (connection.tenant.pk).
"""

import logging
import os
import uuid as uuid_lib

from django.conf import settings
from django.db import connection

from utilidades import backblaze

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


def _validar_archivo(archivo) -> None:
    if archivo.content_type not in TIPOS_PERMITIDOS:
        raise ValueError(f'Tipo de archivo no permitido: {archivo.content_type}')
    if archivo.size > TAMANO_MAXIMO_ARCHIVO:
        raise ValueError(f'El archivo supera el límite de {TAMANO_MAXIMO_ARCHIVO // (1024 * 1024)} MB.')


def _extension(nombre: str) -> str:
    _, ext = os.path.splitext(nombre)
    return ext.lower().lstrip('.')


def subir_archivo(archivo, modelo_id: int, objeto_id: str, archivo_tipo_id: int = 1):
    """
    Valida, sube a B2 y crea un GenArchivo. Retorna la instancia creada.
    """
    from general.models import GenArchivo

    _validar_archivo(archivo)

    cliente_pk = connection.tenant.pk
    nuevo_uuid = uuid_lib.uuid4()
    extension = _extension(archivo.name)
    nombre_archivo = f'{nuevo_uuid}.{extension}' if extension else str(nuevo_uuid)
    key = f'archivos/{cliente_pk}/{modelo_id}/{objeto_id}/{nombre_archivo}'

    backblaze.subir(
        bucket=settings.B2_BUCKET_PUBLICO,
        key=key,
        body=archivo.read(),
        content_type=archivo.content_type,
    )

    url = f'{settings.B2_CDN_URL_PUBLICO.rstrip("/")}/{key}' if settings.B2_CDN_URL_PUBLICO else None

    return GenArchivo.objects.create(
        archivo_tipo_id=archivo_tipo_id,
        modelo_id=modelo_id,
        objeto_id=str(objeto_id),
        nombre=archivo.name,
        tipo=archivo.content_type,
        tamano=archivo.size,
        almacenamiento_id=key,
        uuid=nuevo_uuid,
        url=url,
    )


def eliminar_archivo(gen_archivo) -> None:
    """Elimina el objeto en B2 y borra el GenArchivo de la DB."""
    backblaze.eliminar(settings.B2_BUCKET_PUBLICO, gen_archivo.almacenamiento_id)
    gen_archivo.delete()
