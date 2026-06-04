from django.db import models


class ConConciliacionDetalle(models.Model):
    fecha = models.DateField()
    debito = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    credito = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    detalle = models.CharField(max_length=150, null=True)
    estado_conciliado = models.BooleanField(default=False, db_default=False)
    conciliacion = models.ForeignKey(
        'contabilidad.ConConciliacion', null=True, on_delete=models.PROTECT,
        related_name='conciliaciones_detalles_conciliacion_rel',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta', null=True, on_delete=models.PROTECT,
        related_name='conciliaciones_detalles_cuenta_rel',
    )
    contacto = models.ForeignKey(
        'general.GenContacto', null=True, on_delete=models.PROTECT,
        related_name='conciliaciones_detalles_contacto_rel',
    )
    documento = models.ForeignKey(
        'general.GenDocumento', null=True, on_delete=models.PROTECT,
        related_name='conciliaciones_detalles_documento_rel',
    )

    class Meta:
        db_table = 'con_conciliacion_detalle'
        ordering = ['-id']
        verbose_name = 'Conciliación detalle'
        verbose_name_plural = 'Conciliaciones detalles'

    def __str__(self):
        return str(self.id)
