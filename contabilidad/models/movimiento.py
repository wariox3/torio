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
    centro_costo = models.ForeignKey(
        'contabilidad.ConCentroCosto', null=True, on_delete=models.PROTECT,
        related_name='movimientos_centro_costo_rel',
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
    # Quién y cuándo llevó esta fila al mayor. El movimiento es inmutable —se crea
    # al contabilizar y se borra al descontabilizar, nunca se edita—, así que una
    # sola marca de creación describe su vida entera. Va acá y no en `gen_log`
    # porque los movimientos se escriben con `bulk_create`, que no dispara los
    # signals de auditoría.
    fecha_creacion = models.DateTimeField(null=True, auto_now_add=True)
    usuario = models.ForeignKey(
        'seguridad.SegUsuario', null=True, on_delete=models.PROTECT,
        related_name='movimientos_usuario_rel',
    )

    class Meta:
        db_table = 'con_movimiento'
        ordering = ['-id']
        verbose_name = 'Movimiento'
        verbose_name_plural = 'Movimientos'

    def __str__(self):
        return f'{self.id} - {self.cuenta_id}'
