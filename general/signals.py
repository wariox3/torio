"""
Registro de auditoría: signals que poblan `gen_log` para cualquier modelo
que declare `log_auditoria = True`.

`datos` se deja siempre en null (se reservará para otro uso). Solo se registra
la acción (`crear` / `actualizar` / `eliminar`), el objeto y el usuario.

Limitaciones conscientes:
- `QuerySet.update()`, `bulk_create()`, `bulk_delete()` NO disparan signals.
- Cambios fuera de un request (shell, migraciones) quedan con usuario_id=None.
"""

from django.db import connection
from django.db.models.signals import post_delete, post_save

from seguridad.contexto import obtener_usuario_actual

# Cachés en memoria de IDs, llenadas perezosamente.
#
# La clave lleva el schema porque `gen_accion` y `gen_modelo` son tablas de
# tenant: hay una copia por contenedor y sus ids no tienen por qué coincidir.
# Un proceso atiende a muchos tenants, así que cachear solo por código haría que
# el id sembrado por el primer tenant se reusara en todos los demás, escribiendo
# en `gen_log` FKs que allí apuntan a otra fila o a ninguna.
#
# Hoy `cargar_datos_tenant` siembra los mismos ids fijos en todos los schemas y
# el desajuste no se manifiesta, pero eso es una coincidencia del fixture, no una
# garantía del modelo de datos.
_acciones_cache: dict[tuple[str, str], int] = {}
_modelos_cache: dict[tuple[str, str], int] = {}


def limpiar_caches():
    """
    Vacía las cachés de ids. Pensado para pruebas: los schemas van y vienen
    dentro del mismo proceso y una entrada vieja sobreviviría al schema que la
    originó.
    """
    _acciones_cache.clear()
    _modelos_cache.clear()


def _id_accion(codigo: str) -> int | None:
    """Devuelve el id de GenAccion por código. Cachea para no golpear DB cada vez."""
    clave = (connection.schema_name, codigo)
    if clave not in _acciones_cache:
        from general.models import GenAccion
        try:
            _acciones_cache[clave] = GenAccion.objects.get(codigo=codigo).pk
        except GenAccion.DoesNotExist:
            # El fallo no se cachea a propósito: un tenant recién creado consulta
            # antes de que corran sus fixtures, y cachear el None lo dejaría sin
            # auditoría durante toda la vida del proceso.
            return None
    return _acciones_cache[clave]


def _id_modelo(modelo_cls) -> int | None:
    """Devuelve el id de GenModelo por dotted-path. None si el modelo no está en el catálogo."""
    clave = (
        connection.schema_name,
        f'{modelo_cls._meta.app_label}.{modelo_cls.__name__}',
    )
    if clave not in _modelos_cache:
        from general.models import GenModelo
        try:
            _modelos_cache[clave] = GenModelo.objects.get(
                app=modelo_cls._meta.app_label, clase=modelo_cls.__name__
            ).pk
        except GenModelo.DoesNotExist:
            return None
    return _modelos_cache[clave]


def _datos_usuario():
    usuario = obtener_usuario_actual()
    if usuario is None:
        return None, None
    return usuario.pk, getattr(usuario, 'email', None)


def _crear_log(*, accion_codigo: str, instance, datos=None):
    from general.models import GenLog

    accion_id = _id_accion(accion_codigo)
    modelo_id = _id_modelo(type(instance))
    if accion_id is None or modelo_id is None:
        return
    usuario_id, usuario_correo = _datos_usuario()
    GenLog.objects.create(
        accion_id=accion_id,
        modelo_id=modelo_id,
        objeto_id=str(instance.pk),
        datos=datos,
        usuario_id=usuario_id,
        usuario_correo=usuario_correo,
    )


def _on_post_save(sender, instance, created, **kwargs):
    accion = 'crear' if created else 'actualizar'
    _crear_log(accion_codigo=accion, instance=instance)


def _on_post_delete(sender, instance, **kwargs):
    _crear_log(accion_codigo='eliminar', instance=instance)


def registrar_auditoria(modelo_cls):
    """Conecta los signals de auditoría para un modelo concreto."""
    etiqueta = f'auditoria_{modelo_cls._meta.label_lower}'
    post_save.connect(_on_post_save, sender=modelo_cls, dispatch_uid=f'{etiqueta}_post_save')
    post_delete.connect(_on_post_delete, sender=modelo_cls, dispatch_uid=f'{etiqueta}_post_delete')
