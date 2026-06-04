from django.db import models


class HumTiempo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=200)

    class Meta:
        db_table = 'hum_tiempo'
        ordering = ['nombre']
        verbose_name = 'Tiempo'
        verbose_name_plural = 'Tiempos'

    def __str__(self):
        return self.nombre
