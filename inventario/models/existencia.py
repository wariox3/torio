from django.db import models


class InvExistencia(models.Model):
    """
    Saldo de un item en un almacén.

    Los tres saldos son `DecimalField(20, 6)` y no `FloatField`: se suman contra
    `GenDocumentoDetalle.cantidad_operada` y `GenItem.existencia`, que son
    decimales, y en Python un Decimal más un float revienta. Además el redondeo
    binario del float no sirve para un saldo de inventario.
    """

    existencia = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    remision = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    disponible = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    item = models.ForeignKey(
        'general.GenItem', on_delete=models.PROTECT,
        related_name='existencias_item_rel',
    )
    almacen = models.ForeignKey(
        'inventario.InvAlmacen', on_delete=models.PROTECT,
        related_name='existencias_almacen_rel',
    )

    class Meta:
        db_table = 'inv_existencia'
        ordering = ['-id']
        verbose_name = 'Existencia'
        verbose_name_plural = 'Existencias'
        constraints = [
            # El saldo se busca por (item, almacen) y se crea si no está. Sin la
            # restricción, dos aprobaciones simultáneas del mismo item crean dos
            # filas y el saldo queda partido en dos.
            models.UniqueConstraint(
                fields=['item', 'almacen'], name='inv_existencia_item_almacen_unico',
            ),
        ]

    def __str__(self):
        return f'{self.item_id} - {self.almacen_id}: {self.existencia}'
