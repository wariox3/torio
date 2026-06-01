from django.db import models


class GenDocumentoImpuesto(models.Model):
    base = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    porcentaje = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    porcentaje_base = models.DecimalField(max_digits=20, decimal_places=6, default=100, db_default=100)
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total_operado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    documento_detalle = models.ForeignKey(
        'general.GenDocumentoDetalle',
        on_delete=models.CASCADE,
        related_name='documentos_impuestos_documento_detalle_rel',
    )
    impuesto = models.ForeignKey(
        'general.GenImpuesto',
        on_delete=models.PROTECT,
        related_name='documentos_impuestos_impuesto_rel',
    )

    class Meta:
        db_table = 'gen_documento_impuesto'
        ordering = ['-id']
        verbose_name = 'Documento impuesto'
        verbose_name_plural = 'Documentos impuestos'

    def __str__(self):
        return f'{self.documento_detalle_id} - {self.impuesto_id}'
