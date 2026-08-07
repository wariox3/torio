from django.db import models


class InvAlmacen(models.Model):
    nombre = models.CharField(max_length=80)

    class Meta:
        db_table = 'inv_almacen'
        ordering = ['-id']
        verbose_name = 'Almacén'
        verbose_name_plural = 'Almacenes'

    def __str__(self):
        return self.nombre
