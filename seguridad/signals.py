"""
Un usuario nuevo arranca con todas las aplicaciones (`SegUsuarioAplicacion`).

Va en un signal y no en el serializer de registro porque los usuarios también se
crean con `createsuperuser` y con el manager de django-tenant-users.
"""
from django.db.models.signals import post_save

from contenedor.models import CtnAplicacion
from seguridad.models import SegUsuario, SegUsuarioAplicacion


def _dar_todas_las_aplicaciones(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    SegUsuarioAplicacion.objects.bulk_create(
        [
            SegUsuarioAplicacion(usuario=instance, aplicacion_id=aplicacion_id)
            for aplicacion_id in CtnAplicacion.objects.values_list('id', flat=True)
        ],
        ignore_conflicts=True,
    )


def conectar():
    post_save.connect(
        _dar_todas_las_aplicaciones, sender=SegUsuario,
        dispatch_uid='seguridad_usuario_aplicaciones',
    )
