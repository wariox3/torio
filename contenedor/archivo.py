"""
Adjuntos del schema público: validación, subida a B2 y persistencia en `CtnArchivo`.

Es el par de `general.servicios.archivo` para el master, y reutiliza su validación
de tamaño y tipo real (`validar_archivo`): un adjunto es un adjunto en los dos lados.

Layout en `B2_BUCKET_PRIVADO`, junto al resto de lo del cliente:
    <cliente_pk>/master/<modelo_id>/<uuid>.<ext>

El nombre real se guarda en la fila, no en la ruta. Los archivos perduran: no hay
retención ni borrado.
"""

import logging
import uuid as uuid_lib

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError

from general.servicios.archivo import _extension, validar_archivo
from utilidades import backblaze

logger = logging.getLogger(__name__)


def buscar_objeto(modelo, objeto_id):
    """
    Devuelve el registro dueño del adjunto, o lanza ValueError.

    Solo admiten adjuntos los modelos con `cliente`: es lo que decide quién ve el
    archivo, y un archivo sin dueño quedaría visible para nadie o para todos.
    """
    try:
        clase = apps.get_model(modelo.app, modelo.clase)
    except LookupError:
        raise ValueError(f'El modelo {modelo.app}.{modelo.clase} no existe.')

    if not any(campo.name == 'cliente' for campo in clase._meta.get_fields()):
        raise ValueError(f'{modelo.nombre} no admite adjuntos.')

    try:
        objeto = clase.objects.filter(pk=objeto_id).first()
    except (ValueError, TypeError, DjangoValidationError):
        raise ValueError(f'"{objeto_id}" no es un identificador válido para {modelo.nombre}.')
    if objeto is None:
        raise ValueError(f'No existe {modelo.nombre} con id {objeto_id}.')
    return objeto


def subir(archivo, modelo, objeto, archivo_tipo):
    """
    Valida, sube a B2 y crea el `CtnArchivo` de `objeto`. Devuelve la instancia.

    El `cliente` sale de `objeto`, no del request: así un adjunto no puede quedar
    colgado de un contenedor distinto al de su registro.
    """
    from contenedor.models import CtnArchivo

    tipo = validar_archivo(archivo)

    nuevo_uuid = uuid_lib.uuid4()
    extension = _extension(archivo.name)
    nombre_archivo = f'{nuevo_uuid}.{extension}' if extension else str(nuevo_uuid)
    key = f'{objeto.cliente_id}/master/{modelo.pk}/{nombre_archivo}'

    archivo.seek(0)
    backblaze.subir(
        bucket=settings.B2_BUCKET_PRIVADO,
        key=key,
        body=archivo.read(),
        content_type=tipo,
    )

    try:
        return CtnArchivo.objects.create(
            cliente_id=objeto.cliente_id,
            modelo=modelo,
            objeto_id=str(objeto.pk),
            archivo_tipo=archivo_tipo,
            nombre=archivo.name,
            tipo=tipo,
            tamano=archivo.size,
            almacenamiento_id=key,
            uuid=nuevo_uuid,
        )
    except Exception:
        # El objeto ya está en B2 pero no habrá fila que lo referencie: sin esto
        # queda huérfano para siempre, porque nadie sabe que existe.
        try:
            backblaze.eliminar(settings.B2_BUCKET_PRIVADO, key)
        except Exception:
            logger.error('Quedó un objeto huérfano en B2: %s', key)
        raise
