"""
Toda respuesta de error de la API lleva `detail` con un mensaje legible.

DRF no lo garantiza: un `ValidationError('texto')` sale como `["texto"]` y un
error de serializer como `{"campo": ["mensaje"]}`, así que el front no tenía un
solo lugar de dónde leer el mensaje. Acá se completa `detail` sin quitar nada:
los errores por campo siguen ahí para quien quiera marcar el campo.

Las respuestas que una vista arma a mano no pasan por este manejador, y por eso
la prueba `RespuestasDeErrorTests` revisa que las que llevan un dict literal
traigan `detail`.
"""

from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

MENSAJE_POR_DEFECTO = 'La petición no se pudo procesar.'

# Claves que no son un campo sino el propio mensaje, así que va sin prefijo: la
# de DRF para los errores de `validate()`, y la que usan los clientes de
# servicios externos (`Rededoc`, `Zinc`) para sus fallas de red.
CAMPOS_SIN_PREFIJO = ('non_field_errors', 'mensaje')


def manejador_excepciones(exc, context):
    if isinstance(exc, (ProtectedError, RestrictedError)):
        return Response({'detail': mensaje_protegido(exc)}, status=status.HTTP_400_BAD_REQUEST)
    respuesta = exception_handler(exc, context)
    if respuesta is not None:
        respuesta.data = con_detail(respuesta.data)
    return respuesta


def mensaje_protegido(exc):
    """
    Mensaje para un borrado que la base no permite porque otros registros apuntan
    con `PROTECT` o `RESTRICT` a lo que se quería borrar.

    Es el respaldo: sin esto el error salía como un 500. La vista que conoce su
    caso (la novedad que está en una nómina) da un mensaje más preciso antes.
    """
    objetos = getattr(exc, 'protected_objects', None) or getattr(exc, 'restricted_objects', None) or ()
    modelos = sorted({str(objeto._meta.verbose_name) for objeto in objetos})
    if not modelos:
        return 'No se puede eliminar: otros registros lo usan.'
    return f'No se puede eliminar: lo usan registros de {", ".join(modelos)}.'


def con_detail(datos):
    """
    Devuelve el cuerpo de error con `detail`, conservando lo que ya traía.

    - Un dict que ya tiene `detail` pasa tal cual.
    - Un dict de errores por campo gana `detail` con el primer mensaje, prefijado
      con su campo: `{"ids": [...]}` → `"ids: Este campo es requerido."`.
    - Una lista de mensajes se vuelve `{"detail": "uno dos"}`.
    """
    if isinstance(datos, dict):
        if 'detail' in datos:
            return datos
        return {'detail': _primer_mensaje(datos) or MENSAJE_POR_DEFECTO, **datos}
    if isinstance(datos, list):
        mensajes = [m for m in (_primer_mensaje(item) for item in datos) if m]
        return {'detail': ' '.join(mensajes) or MENSAJE_POR_DEFECTO}
    if isinstance(datos, str) and datos:
        return {'detail': datos}
    return {'detail': MENSAJE_POR_DEFECTO}


def _primer_mensaje(valor, campo=None):
    if isinstance(valor, str):
        return f'{campo}: {valor}' if campo and campo not in CAMPOS_SIN_PREFIJO else valor
    if isinstance(valor, list):
        for item in valor:
            mensaje = _primer_mensaje(item, campo)
            if mensaje:
                return mensaje
    if isinstance(valor, dict):
        for clave, item in valor.items():
            ruta = clave if campo is None or campo in CAMPOS_SIN_PREFIJO else f'{campo}.{clave}'
            mensaje = _primer_mensaje(item, ruta)
            if mensaje:
                return mensaje
    return None
