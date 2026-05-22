from django.db import models


class GenPrecio(models.Model):
    nombre = models.CharField(max_length=200)
    venta = models.BooleanField(default=False, db_default=False)
    compra = models.BooleanField(default=False, db_default=False)
    fecha_vence = models.DateField()

    class Meta:
        db_table = 'gen_precio'
        ordering = ['-id']
        verbose_name = 'Precio'
        verbose_name_plural = 'Precios'

    def __str__(self):
        return self.nombre
