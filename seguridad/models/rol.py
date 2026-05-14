from django.db import models


class SegRol(models.Model):
    nombre = models.CharField(max_length=50, unique=True, db_index=True)
    codigo = models.CharField(max_length=20, unique=True, null=True)
    descripcion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    permisos = models.ManyToManyField(
        'seguridad.SegPermiso',
        through='seguridad.SegRolPermiso',
        related_name='roles',
        blank=True,
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'seg_rol'
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre
