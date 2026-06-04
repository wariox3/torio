from django.db import models


class HumRiesgo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=100)
    porcentaje = models.DecimalField(max_digits=6, decimal_places=3, default=0, db_default=0)

    class Meta:
        db_table = 'hum_riesgo'
        ordering = ['nombre']
        verbose_name = 'Riesgo'
        verbose_name_plural = 'Riesgos'

    def __str__(self):
        return self.nombre
