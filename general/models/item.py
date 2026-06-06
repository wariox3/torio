from django.db import models


class GenItem(models.Model):
    nombre = models.CharField(max_length=200)
    codigo = models.CharField(max_length=100, null=True)
    referencia = models.CharField(max_length=50, null=True)
    costo_promedio = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    costo_total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    costo = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    precio = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    producto = models.BooleanField(default=False, db_default=False)
    servicio = models.BooleanField(default=False, db_default=False)
    inventario = models.BooleanField(default=False, db_default=False)
    negativo = models.BooleanField(default=False, db_default=False)
    favorito = models.BooleanField(default=False, db_default=False)
    venta = models.BooleanField(default=True, db_default=True)
    inactivo = models.BooleanField(default=False, db_default=False)
    existencia = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    remision = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    disponible = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    imagen = models.TextField(null=True)
    cuenta_venta = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='itemes_cuenta_venta_rel',
    )
    cuenta_compra = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='itemes_cuenta_compra_rel',
    )
    cuenta_costo_venta = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='itemes_cuenta_costo_venta_rel',
    )
    cuenta_inventario = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='itemes_cuenta_inventario_rel',
    )

    class Meta:
        db_table = 'gen_item'
        ordering = ['-id']
        verbose_name = 'Item'
        verbose_name_plural = 'Items'

    def __str__(self):
        return self.nombre
