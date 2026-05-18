from django.db import models


class GenDocumentoTipo(models.Model):
    nombre = models.CharField(max_length=100)
    consecutivo = models.IntegerField(default=1, db_default=1)
    venta = models.BooleanField(default=False, db_default=False)
    compra = models.BooleanField(default=False, db_default=False)
    cobrar = models.BooleanField(default=False, db_default=False)
    pagar = models.BooleanField(default=False, db_default=False)
    electronico = models.BooleanField(default=False, db_default=False)
    contabilidad = models.BooleanField(default=False, db_default=False)
    inventario = models.BooleanField(default=False, db_default=False)
    pos = models.BooleanField(default=False, db_default=False)
    operacion = models.BigIntegerField(default=0, db_default=0)
    operacion_inventario = models.BigIntegerField(default=0, db_default=0)
    operacion_remision = models.BigIntegerField(default=0, db_default=0)
    afecta_cantidad = models.BooleanField(default=False, db_default=False)
    documento_clase = models.ForeignKey(
        'general.GenDocumentoClase',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_tipos_documento_clase',
    )
    resolucion = models.ForeignKey(
        'general.GenResolucion',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_tipos_resolucion',
    )
    cuenta_cobrar = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_tipos_cuenta_cobrar',
    )
    cuenta_pagar = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_tipos_cuenta_pagar',
    )
    comprobante = models.ForeignKey(
        'contabilidad.ConComprobante',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_tipos_comprobante_rel',
    )

    class Meta:
        db_table = 'gen_documento_tipo'
        ordering = ['nombre']
        verbose_name = 'Tipo de documento'
        verbose_name_plural = 'Tipos de documento'

    def __str__(self):
        return self.nombre
