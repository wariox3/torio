from django.db import models


class HumAporteEntidad(models.Model):
    tipo = models.CharField(max_length=20)
    cotizacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    aporte = models.ForeignKey(
        'humano.HumAporte', on_delete=models.PROTECT,
        related_name='aportes_entidades_aporte_rel',
    )
    entidad = models.ForeignKey(
        'humano.HumEntidad', on_delete=models.PROTECT,
        related_name='aportes_entidades_entidad_rel',
    )

    class Meta:
        db_table = 'hum_aporte_entidad'
        ordering = ['-id']
        verbose_name = 'Aporte entidad'
        verbose_name_plural = 'Aportes entidades'

    def __str__(self):
        return f'{self.id} - {self.tipo}'
