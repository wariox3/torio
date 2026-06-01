from django.db import models


class GenImpuesto(models.Model):
    nombre = models.CharField(max_length=20)
    nombre_extendido = models.CharField(max_length=100)
    porcentaje = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    porcentaje_base = models.DecimalField(max_digits=10, decimal_places=2, default=100, db_default=100)
    operacion = models.IntegerField(default=1, db_default=1)
    venta = models.BooleanField(default=True, db_default=True)
    compra = models.BooleanField(default=True, db_default=True)
    impuesto_tipo = models.ForeignKey(
        'general.GenImpuestoTipo',
        null=True,
        on_delete=models.PROTECT,
        related_name='impuestos_impuesto_tipo_rel',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='impuestos_cuenta_rel',
    )

    class Meta:
        db_table = 'gen_impuesto'
        ordering = ['id', 'impuesto_tipo_id']
        verbose_name = 'Impuesto'
        verbose_name_plural = 'Impuestos'

    def __str__(self):
        return self.nombre
