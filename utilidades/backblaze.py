import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from PIL import Image

from utilidades.imagenes import (
    a_bytes_jpeg,
    recortar_cuadrado,
    redimensionar,
    validar_archivo_imagen,
)

logger = logging.getLogger(__name__)


def _cliente_s3():
    return boto3.client(
        's3',
        endpoint_url=settings.B2_ENDPOINT_URL,
        aws_access_key_id=settings.B2_KEY_ID,
        aws_secret_access_key=settings.B2_APP_KEY,
    )


def subir(bucket: str, key: str, body: bytes, content_type: str) -> None:
    """Sube un objeto a B2. Propaga errores tras loguearlos."""
    try:
        _cliente_s3().put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
    except (BotoCoreError, ClientError) as e:
        logger.error('Error subiendo a B2 (bucket=%s key=%s): %s', bucket, key, e)
        raise


def eliminar(bucket: str, key: str) -> None:
    """Elimina un objeto de B2. Propaga errores tras loguearlos."""
    try:
        _cliente_s3().delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as e:
        logger.error('Error eliminando de B2 (bucket=%s key=%s): %s', bucket, key, e)
        raise


def subir_foto_usuario(archivo, user_id: int) -> tuple[str, str]:
    """
    Valida, procesa y sube la foto de perfil a Backblaze B2.
    Retorna (key_original, key_thumbnail).
    """
    validar_archivo_imagen(archivo)

    imagen = Image.open(archivo).convert('RGB')

    original_bytes = a_bytes_jpeg(redimensionar(imagen.copy(), 800))
    thumbnail_bytes = a_bytes_jpeg(recortar_cuadrado(imagen.copy(), 150), calidad=80)

    key_original = f'usuarios/{user_id}/foto.jpg'
    key_thumbnail = f'usuarios/{user_id}/foto_thumbnail.jpg'

    subir(settings.B2_BUCKET_PUBLICO, key_original, original_bytes, 'image/jpeg')
    subir(settings.B2_BUCKET_PUBLICO, key_thumbnail, thumbnail_bytes, 'image/jpeg')

    return key_original, key_thumbnail
