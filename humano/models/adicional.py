from django.db import models


class HumAdicional(models.Model):
    valor = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    horas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    aplica_dia_laborado = models.BooleanField(default=False, db_default=False)
    inactivo = models.BooleanField(default=False, db_default=False)
    permanente = models.BooleanField(default=False, db_default=False)
    detalle = models.CharField(max_length=150, null=True)
    programacion = models.ForeignKey(
        'humano.HumProgramacion', null=True, on_delete=models.PROTECT,
        related_name='adicionales_programacion_rel',
    )
    concepto = models.ForeignKey(
        'humano.HumConcepto', on_delete=models.PROTECT,
        related_name='adicionales_concepto_rel',
    )
    contrato = models.ForeignKey(
        'humano.HumContrato', on_delete=models.PROTECT,
        related_name='adicionales_contrato_rel',
    )

    class Meta:
        db_table = 'hum_adicional'
        ordering = ['-id']
        verbose_name = 'Adicional'
        verbose_name_plural = 'Adicionales'

    def __str__(self):
        return f'{self.id} - {self.concepto_id}'
