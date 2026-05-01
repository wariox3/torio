from django.db import models


class SegPermiso(models.Model):
    codigo = models.CharField(max_length=100, unique=True, db_index=True)
    nombre = models.CharField(max_length=150)
    modulo = models.CharField(max_length=50, db_index=True)
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'seg_permiso'
        verbose_name = 'Permiso'
        verbose_name_plural = 'Permisos'
        ordering = ['modulo', 'codigo']

    def __str__(self):
        return self.codigo
