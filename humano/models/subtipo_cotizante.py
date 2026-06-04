from django.db import models


class HumSubtipoCotizante(models.Model):
    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=200)

    class Meta:
        db_table = 'hum_subtipo_cotizante'
        ordering = ['nombre']
        verbose_name = 'Subtipo cotizante'
        verbose_name_plural = 'Subtipos cotizantes'

    def __str__(self):
        return self.nombre
