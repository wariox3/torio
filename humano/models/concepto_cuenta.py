from django.db import models


class HumConceptoCuenta(models.Model):
    concepto = models.ForeignKey(
        'humano.HumConcepto', on_delete=models.PROTECT,
        related_name='conceptos_cuentas_concepto_rel',
    )
    tipo_costo = models.ForeignKey(
        'humano.HumTipoCosto', on_delete=models.PROTECT,
        related_name='conceptos_cuentas_tipo_costo_rel',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta', on_delete=models.PROTECT,
        related_name='conceptos_cuentas_cuenta_rel',
    )

    class Meta:
        db_table = 'hum_concepto_cuenta'
        ordering = ['-id']
        verbose_name = 'Concepto cuenta'
        verbose_name_plural = 'Conceptos cuentas'

    def __str__(self):
        return f'{self.concepto_id} - {self.cuenta_id}'
