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


def subir_foto_usuario(archivo, user_id: int) -> tuple[str, str]:
    """
    Valida, procesa y sube la foto de perfil a Backblaze B2.
    Retorna (url_original, url_thumbnail).
    """
    validar_archivo_imagen(archivo)

    imagen = Image.open(archivo).convert('RGB')

    original_bytes = a_bytes_jpeg(redimensionar(imagen.copy(), 800))
    thumbnail_bytes = a_bytes_jpeg(recortar_cuadrado(imagen.copy(), 150), calidad=80)

    key_original = f'usuarios/{user_id}/foto.jpg'
    key_thumbnail = f'usuarios/{user_id}/foto_thumbnail.jpg'

    try:
        s3 = _cliente_s3()
        s3.put_object(
            Bucket=settings.B2_BUCKET_PUBLICO,
            Key=key_original,
            Body=original_bytes,
            ContentType='image/jpeg',
        )
        s3.put_object(
            Bucket=settings.B2_BUCKET_PUBLICO,
            Key=key_thumbnail,
            Body=thumbnail_bytes,
            ContentType='image/jpeg',
        )
    except (BotoCoreError, ClientError) as e:
        logger.error('Error subiendo foto a B2 para usuario %s: %s', user_id, e)
        raise

    return key_original, key_thumbnail
