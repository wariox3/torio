from django.db import models


class SegRolPermiso(models.Model):
    rol = models.ForeignKey(
        'seguridad.SegRol', on_delete=models.CASCADE, db_column='rol_id', related_name='rol_permisos',
    )
    permiso = models.ForeignKey(
        'seguridad.SegPermiso', on_delete=models.CASCADE, db_column='permiso_id', related_name='rol_permisos',
    )

    class Meta:
        db_table = 'seg_rol_permiso'
        verbose_name = 'Rol-Permiso'
        verbose_name_plural = 'Rol-Permisos'
        unique_together = [['rol', 'permiso']]
