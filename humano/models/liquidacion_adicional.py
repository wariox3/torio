from django.db import models


class HumLiquidacionAdicional(models.Model):
    adicional = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    deduccion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    detalle = models.CharField(max_length=150, null=True)
    concepto = models.ForeignKey(
        'humano.HumConcepto', on_delete=models.PROTECT,
        related_name='liquidaciones_adicionales_concepto_rel',
    )
    liquidacion = models.ForeignKey(
        'humano.HumLiquidacion', on_delete=models.PROTECT,
        related_name='liquidaciones_adicionales_liquidacion_rel',
    )

    class Meta:
        db_table = 'hum_liquidacion_adicional'
        ordering = ['-id']
        verbose_name = 'Liquidación adicional'
        verbose_name_plural = 'Liquidaciones adicionales'

    def __str__(self):
        return f'{self.id} - {self.concepto_id}'
