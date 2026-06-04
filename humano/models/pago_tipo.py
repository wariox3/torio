from django.db import models


class HumPagoTipo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100)
    aplica_programacion = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'hum_pago_tipo'
        ordering = ['nombre']
        verbose_name = 'Pago tipo'
        verbose_name_plural = 'Pagos tipos'

    def __str__(self):
        return self.nombre
