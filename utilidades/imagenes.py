"""
Procesamiento de imágenes subidas por usuarios.

Todo lo de acá asume que el archivo es hostil hasta que se demuestre lo
contrario: el tipo lo declara el cliente y las dimensiones no se conocen hasta
abrir el header.
"""

import io

from PIL import Image, ImageOps

from utilidades import mime

FORMATOS_PERMITIDOS = {'image/jpeg', 'image/png', 'image/webp'}
TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB

# Un PNG de 0.42 MB puede declarar 12000x12000 y ocupar 412 MB de RAM al
# decodificarse: el límite de bytes no protege de nada por sí solo. PIL avisa
# recién a los 89 megapíxeles y no aborta hasta el doble, así que el corte se
# hace acá, antes de tocar los píxeles.
MAX_PIXELES = 40_000_000  # 40 MP ≈ una foto de 7750x5160

LADO_MAXIMO_ORIGINAL = 1024
LADO_THUMBNAIL = 320
CALIDAD_ORIGINAL = 85
CALIDAD_THUMBNAIL = 82


def validar_archivo_imagen(archivo) -> None:
    """
    Valida formato, tamaño y que el contenido sea lo que dice ser.

    Lanza ValueError si no cumple. Deja el puntero al inicio.
    """
    if archivo.content_type not in FORMATOS_PERMITIDOS:
        raise ValueError('Formato no permitido. Usa JPEG, PNG o WEBP.')
    if archivo.size > TAMANO_MAXIMO:
        raise ValueError('El archivo supera el límite de 5 MB.')

    archivo.seek(0)
    posibles = mime.tipos_posibles(archivo.read())
    archivo.seek(0)
    if archivo.content_type not in posibles:
        raise ValueError('El contenido del archivo no corresponde a una imagen válida.')


def abrir_imagen(archivo) -> Image.Image:
    """
    Abre la imagen dejándola derecha y sin transparencia.

    `Image.open` solo lee el header, así que las dimensiones se revisan antes de
    decodificar nada. Después:

    - `exif_transpose` aplica la orientación que graban los celulares; sin esto
      una foto apaisada se sirve rotada 90°.
    - el canal alfa se compone sobre blanco. Descartarlo sin componer deja a la
      vista los bytes RGB que había debajo, que suelen ser negros.
    """
    archivo.seek(0)
    try:
        imagen = Image.open(archivo)
    except Exception as e:
        raise ValueError('El archivo no es una imagen que se pueda leer.') from e

    ancho, alto = imagen.size
    if ancho * alto > MAX_PIXELES:
        raise ValueError(
            f'La imagen es demasiado grande ({ancho}x{alto}). '
            f'El máximo es {MAX_PIXELES // 1_000_000} megapíxeles.'
        )

    try:
        imagen = ImageOps.exif_transpose(imagen)
        return _aplanar(imagen)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError('El archivo no es una imagen que se pueda leer.') from e


def _aplanar(imagen: Image.Image) -> Image.Image:
    """Compone sobre blanco lo que tenga transparencia y devuelve RGB."""
    if imagen.mode == 'P':
        imagen = imagen.convert('RGBA')
    if imagen.mode in ('RGBA', 'LA'):
        fondo = Image.new('RGB', imagen.size, (255, 255, 255))
        fondo.paste(imagen, mask=imagen.getchannel('A'))
        return fondo
    return imagen.convert('RGB')


def redimensionar(imagen: Image.Image, lado_max: int) -> Image.Image:
    imagen.thumbnail((lado_max, lado_max), Image.LANCZOS)
    return imagen


def recortar_cuadrado(imagen: Image.Image, lado: int) -> Image.Image:
    ancho, alto = imagen.size
    minimo = min(ancho, alto)
    izq = (ancho - minimo) // 2
    sup = (alto - minimo) // 2
    imagen = imagen.crop((izq, sup, izq + minimo, sup + minimo))
    return imagen.resize((lado, lado), Image.LANCZOS)


def a_bytes_jpeg(imagen: Image.Image, calidad: int = 85) -> bytes:
    buffer = io.BytesIO()
    imagen.save(buffer, format='JPEG', quality=calidad, optimize=True)
    return buffer.getvalue()


def a_bytes_webp(imagen: Image.Image, calidad: int = 85) -> bytes:
    buffer = io.BytesIO()
    imagen.save(buffer, format='WEBP', quality=calidad, method=4)
    return buffer.getvalue()
