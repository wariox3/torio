from django.db import models


class HumSucursal(models.Model):
    nombre = models.CharField(max_length=80)
    codigo = models.CharField(max_length=10, null=True)

    class Meta:
        db_table = 'hum_sucursal'
        ordering = ['nombre']
        verbose_name = 'Sucursal'
        verbose_name_plural = 'Sucursales'

    def __str__(self):
        return self.nombre
