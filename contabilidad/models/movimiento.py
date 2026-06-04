from django.db import models


class ConMovimiento(models.Model):
    numero = models.IntegerField(null=True)
    fecha = models.DateField()
    debito = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    credito = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    naturaleza = models.CharField(max_length=1)
    detalle = models.CharField(max_length=150, null=True)
    cierre = models.BooleanField(default=False, db_default=False)
    saldo_inicial = models.BooleanField(default=False, db_default=False)
    comprobante = models.ForeignKey(
        'contabilidad.ConComprobante', on_delete=models.PROTECT,
        related_name='movimientos_comprobante_rel',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta', on_delete=models.PROTECT,
        related_name='movimientos_cuenta_rel',
    )
    grupo = models.ForeignKey(
        'contabilidad.ConCentroCosto', null=True, on_delete=models.PROTECT,
        related_name='movimientos_grupo_rel',
    )
    periodo = models.ForeignKey(
        'contabilidad.ConPeriodo', on_delete=models.PROTECT,
        related_name='movimientos_periodo_rel',
    )
    contacto = models.ForeignKey(
        'general.GenContacto', null=True, on_delete=models.PROTECT,
        related_name='movimientos_contacto_rel',
    )
    documento = models.ForeignKey(
        'general.GenDocumento', null=True, on_delete=models.PROTECT,
        related_name='movimientos_documento_rel',
    )

    class Meta:
        db_table = 'con_movimiento'
        ordering = ['-id']
        verbose_name = 'Movimiento'
        verbose_name_plural = 'Movimientos'

    def __str__(self):
        return f'{self.id} - {self.cuenta_id}'
