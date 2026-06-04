from django.db import models


class HumCargo(models.Model):
    codigo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=200)
    estado_inactivo = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'hum_cargo'
        ordering = ['nombre']
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'

    def __str__(self):
        return self.nombre
