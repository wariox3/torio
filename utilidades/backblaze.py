import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from PIL import Image
from rest_framework import status
from rest_framework.exceptions import APIException

from utilidades.imagenes import (
    a_bytes_jpeg,
    recortar_cuadrado,
    redimensionar,
    validar_archivo_imagen,
)

logger = logging.getLogger(__name__)


class ErrorDeAlmacenamiento(APIException):
    """
    B2 no respondió o rechazó la operación.

    Hereda de APIException para que DRF la traduzca sola en cualquier vista: un
    corte de red contra B2 es un fallo de un servicio de terceros, no un error
    del cliente ni un bug nuestro, y sin esto sale como 500 con traceback.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'Falló la unidad de almacenamiento.'
    default_code = 'error_almacenamiento'


def _cliente_s3():
    return boto3.client(
        's3',
        endpoint_url=settings.B2_ENDPOINT_URL,
        aws_access_key_id=settings.B2_KEY_ID,
        aws_secret_access_key=settings.B2_APP_KEY,
    )


def subir(bucket: str, key: str, body: bytes, content_type: str) -> None:
    """Sube un objeto a B2. Lanza ErrorDeAlmacenamiento (502) si B2 falla."""
    try:
        _cliente_s3().put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
    except (BotoCoreError, ClientError) as e:
        logger.error('Error subiendo a B2 (bucket=%s key=%s): %s', bucket, key, e)
        raise ErrorDeAlmacenamiento() from e


class ArchivoNoEncontrado(APIException):
    """
    La fila existe pero el objeto ya no está en B2.

    Es un 404 y no un 502: el almacenamiento respondió bien, lo que no hay es
    el archivo. Pasa si alguien lo borró por fuera de la aplicación.
    """

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = 'El archivo ya no está en la unidad de almacenamiento.'
    default_code = 'archivo_no_encontrado'


def descargar(bucket: str, key: str) -> bytes:
    """Trae el contenido de un objeto de B2. Lanza ErrorDeAlmacenamiento (502) si B2 falla."""
    try:
        return _cliente_s3().get_object(Bucket=bucket, Key=key)['Body'].read()
    except ClientError as e:
        codigo = e.response.get('Error', {}).get('Code')
        if codigo in ('NoSuchKey', '404'):
            logger.warning('Objeto ausente en B2 (bucket=%s key=%s)', bucket, key)
            raise ArchivoNoEncontrado() from e
        logger.error('Error descargando de B2 (bucket=%s key=%s): %s', bucket, key, e)
        raise ErrorDeAlmacenamiento() from e
    except BotoCoreError as e:
        logger.error('Error descargando de B2 (bucket=%s key=%s): %s', bucket, key, e)
        raise ErrorDeAlmacenamiento() from e


def eliminar(bucket: str, key: str) -> None:
    """Elimina un objeto de B2. Lanza ErrorDeAlmacenamiento (502) si B2 falla."""
    try:
        _cliente_s3().delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as e:
        logger.error('Error eliminando de B2 (bucket=%s key=%s): %s', bucket, key, e)
        raise ErrorDeAlmacenamiento() from e


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
