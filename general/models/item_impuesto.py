from django.db import models


class GenItemImpuesto(models.Model):
    item = models.ForeignKey(
        'general.GenItem',
        on_delete=models.CASCADE,
        related_name='items_impuestos_item_rel',
    )
    impuesto = models.ForeignKey(
        'general.GenImpuesto',
        on_delete=models.PROTECT,
        related_name='items_impuestos_impuesto_rel',
    )

    class Meta:
        db_table = 'gen_item_impuesto'
        ordering = ['-id']
        unique_together = ('item', 'impuesto')
        verbose_name = 'Item impuesto'
        verbose_name_plural = 'Items impuestos'

    def __str__(self):
        return f'{self.item_id} - {self.impuesto_id}'
