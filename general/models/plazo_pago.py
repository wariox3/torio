from django.db import models


class GenPlazoPago(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    dias = models.IntegerField(default=0, db_default=0)

    class Meta:
        db_table = 'gen_plazo_pago'
        ordering = ['dias']
        verbose_name = 'Plazo de pago'
        verbose_name_plural = 'Plazos de pago'

    def __str__(self):
        return self.nombre
