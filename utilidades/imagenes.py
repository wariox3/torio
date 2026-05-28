import io

from PIL import Image

FORMATOS_PERMITIDOS = {'image/jpeg', 'image/png', 'image/webp'}
TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB


def validar_archivo_imagen(archivo) -> None:
    """Valida formato y tamaño. Lanza ValueError si no cumple."""
    if archivo.content_type not in FORMATOS_PERMITIDOS:
        raise ValueError('Formato no permitido. Usa JPEG, PNG o WEBP.')
    if archivo.size > TAMANO_MAXIMO:
        raise ValueError('El archivo supera el límite de 5 MB.')


def redimensionar(imagen: Image.Image, lado_max: int) -> Image.Image:
    imagen.thumbnail((lado_max, lado_max), Image.LANCZOS)
    return imagen


def recortar_cuadrado(imagen: Image.Image, lado: int) -> Image.Image:
    ancho, alto = imagen.size
    minimo = min(ancho, alto)
    izq = (ancho - minimo) // 2
    sup = (alto - minimo) // 2
    imagen = imagen.crop((izq, sup, izq + minimo, sup + minimo))
    imagen = imagen.resize((lado, lado), Image.LANCZOS)
    return imagen


def a_bytes_jpeg(imagen: Image.Image, calidad: int = 85) -> bytes:
    buffer = io.BytesIO()
    imagen.save(buffer, format='JPEG', quality=calidad, optimize=True)
    return buffer.getvalue()
