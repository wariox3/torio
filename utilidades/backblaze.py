import io
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

_FORMATOS_PERMITIDOS = {'image/jpeg', 'image/png', 'image/webp'}
_TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB
_LADO_ORIGINAL = 800
_LADO_THUMBNAIL = 150


def _cliente_s3():
    return boto3.client(
        's3',
        endpoint_url=settings.B2_ENDPOINT_URL,
        aws_access_key_id=settings.B2_KEY_ID,
        aws_secret_access_key=settings.B2_APP_KEY,
    )


def _redimensionar(imagen: Image.Image, lado_max: int) -> Image.Image:
    imagen.thumbnail((lado_max, lado_max), Image.LANCZOS)
    return imagen


def _recortar_cuadrado(imagen: Image.Image, lado: int) -> Image.Image:
    ancho, alto = imagen.size
    minimo = min(ancho, alto)
    izq = (ancho - minimo) // 2
    sup = (alto - minimo) // 2
    imagen = imagen.crop((izq, sup, izq + minimo, sup + minimo))
    imagen = imagen.resize((lado, lado), Image.LANCZOS)
    return imagen


def _a_bytes(imagen: Image.Image, calidad: int = 85) -> bytes:
    buffer = io.BytesIO()
    imagen.save(buffer, format='JPEG', quality=calidad, optimize=True)
    return buffer.getvalue()


def subir_foto_usuario(archivo, user_id: int) -> tuple[str, str]:
    """
    Valida, procesa y sube la foto de perfil a Backblaze B2.
    Retorna (url_original, url_thumbnail).
    """
    if archivo.content_type not in _FORMATOS_PERMITIDOS:
        raise ValueError('Formato no permitido. Usa JPEG, PNG o WEBP.')

    if archivo.size > _TAMANO_MAXIMO:
        raise ValueError('El archivo supera el límite de 5 MB.')

    imagen = Image.open(archivo).convert('RGB')

    original_bytes = _a_bytes(_redimensionar(imagen.copy(), _LADO_ORIGINAL))
    thumbnail_bytes = _a_bytes(_recortar_cuadrado(imagen.copy(), _LADO_THUMBNAIL), calidad=80)

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
