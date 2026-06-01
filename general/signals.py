"""
Registro de auditoría: signals que poblan `gen_log` para cualquier modelo
que declare `log_auditoria = True`.

`datos` se deja siempre en null (se reservará para otro uso). Solo se registra
la acción (`crear` / `actualizar` / `eliminar`), el objeto y el usuario.

Limitaciones conscientes:
- `QuerySet.update()`, `bulk_create()`, `bulk_delete()` NO disparan signals.
- Cambios fuera de un request (shell, migraciones) quedan con usuario_id=None.
"""

from django.db.models.signals import post_delete, post_save

from seguridad.contexto import obtener_usuario_actual

# Cachés en memoria de IDs por código/dotted-path (se llenan perezosamente).
_acciones_cache: dict[str, int] = {}
_modelos_cache: dict[str, int] = {}


def _id_accion(codigo: str) -> int | None:
    """Devuelve el id de GenAccion por código. Cachea para no golpear DB cada vez."""
    if codigo not in _acciones_cache:
        from general.models import GenAccion
        try:
            _acciones_cache[codigo] = GenAccion.objects.get(codigo=codigo).pk
        except GenAccion.DoesNotExist:
            return None
    return _acciones_cache[codigo]


def _id_modelo(modelo_cls) -> int | None:
    """Devuelve el id de GenModelo por dotted-path. None si el modelo no está en el catálogo."""
    clave = f'{modelo_cls._meta.app_label}.{modelo_cls.__name__}'
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
