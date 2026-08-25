from django.db import models


class GenPrecioDetalle(models.Model):
    vr_precio = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    precio = models.ForeignKey(
        'general.GenPrecio',
        on_delete=models.PROTECT,
        related_name='detalles',
    )
    item = models.ForeignKey(
        'general.GenItem',
        on_delete=models.PROTECT,
        related_name='precios_detalles_item_rel',
    )

    class Meta:
        db_table = 'gen_precio_detalle'
        ordering = ['-id']
        verbose_name = 'Precio detalle'
        verbose_name_plural = 'Precios detalles'
        constraints = [
            models.UniqueConstraint(
                fields=['precio', 'item'],
                name='gen_precio_detalle_precio_item_unico',
            ),
        ]

    def __str__(self):
        return f'{self.precio_id} - {self.id}'
