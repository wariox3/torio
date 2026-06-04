from django.db import models


class HumContratoTipo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100)

    class Meta:
        db_table = 'hum_contrato_tipo'
        ordering = ['nombre']
        verbose_name = 'Contrato tipo'
        verbose_name_plural = 'Contratos tipos'

    def __str__(self):
        return self.nombre
