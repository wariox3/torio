from django.db import models


class HumCredito(models.Model):
    fecha_inicio = models.DateField()
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cuota = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    abono = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    saldo = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cantidad_cuotas = models.IntegerField(default=0, db_default=0)
    cuota_actual = models.IntegerField(default=0, db_default=0)
    validar_cuotas = models.BooleanField(default=True, db_default=True)
    inactivo = models.BooleanField(default=False, db_default=False)
    pagado = models.BooleanField(default=False, db_default=False)
    aplica_prima = models.BooleanField(default=False, db_default=False)
    aplica_cesantia = models.BooleanField(default=False, db_default=False)
    comentario = models.CharField(max_length=300, null=True)
    concepto = models.ForeignKey(
        'humano.HumConcepto', null=True, on_delete=models.PROTECT,
        related_name='creditos_concepto_rel',
    )
    contrato = models.ForeignKey(
        'humano.HumContrato', on_delete=models.PROTECT,
        related_name='creditos_contrato_rel',
    )

    class Meta:
        db_table = 'hum_credito'
        ordering = ['-id']
        verbose_name = 'Crédito'
        verbose_name_plural = 'Créditos'

    def __str__(self):
        return f'{self.id} - {self.contrato_id}'
