from decimal import Decimal

from django.db import models


class GenDocumentoDetalle(models.Model):
    tipo_registro = models.CharField(max_length=1, default='I', db_default='I')
    cantidad = models.FloatField(default=0, db_default=0)
    cantidad_operada = models.FloatField(default=0, db_default=0)
    cantidad_afectada = models.FloatField(default=0, db_default=0)
    cantidad_pendiente = models.FloatField(default=0, db_default=0)
    costo = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    precio = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pago = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pago_operado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    subtotal = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    descuento = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total_bruto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_impuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    impuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    impuesto_retencion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    impuesto_operado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    hora = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    horas = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    horas_diurnas = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    horas_nocturnas = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    hora_desde = models.TimeField(null=True)
    hora_hasta = models.TimeField(null=True)
    lunes = models.BooleanField(default=False, db_default=False)
    martes = models.BooleanField(default=False, db_default=False)
    miercoles = models.BooleanField(default=False, db_default=False)
    jueves = models.BooleanField(default=False, db_default=False)
    viernes = models.BooleanField(default=False, db_default=False)
    sabado = models.BooleanField(default=False, db_default=False)
    domingo = models.BooleanField(default=False, db_default=False)
    festivo = models.BooleanField(default=False, db_default=False)
    programar = models.BooleanField(default=False, db_default=False)
    cortesia = models.BooleanField(default=False, db_default=False)
    compuesto = models.BooleanField(default=False, db_default=False)
    dias = models.BigIntegerField(default=0, db_default=0)
    base_cotizacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_prestacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_prestacion_vacacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    porcentaje = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    porcentaje_descuento = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    devengado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    deduccion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    naturaleza = models.CharField(max_length=1, null=True)
    operacion = models.BigIntegerField(default=0, db_default=0)
    operacion_inventario = models.BigIntegerField(default=0, db_default=0)
    operacion_remision = models.BigIntegerField(default=0, db_default=0)
    detalle = models.CharField(max_length=150, null=True)
    numero = models.IntegerField(null=True)
    documento = models.ForeignKey(
        'general.GenDocumento',
        on_delete=models.PROTECT,
        related_name='documentos_detalles_documento_rel',
    )
    documento_afectado = models.ForeignKey(
        'general.GenDocumento',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_detalles_documento_afectado_rel',
    )
    documento_detalle_afectado = models.ForeignKey(
        'self',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_detalles_documento_detalle_afectado_rel',
    )
    item = models.ForeignKey(
        'general.GenItem',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_detalles_item_rel',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_detalles_cuenta_rel',
    )
    contacto = models.ForeignKey(
        'general.GenContacto',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_detalles_contacto_rel',
    )
    modalidad = models.ForeignKey(
        'general.GenModalidad',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_detalles_modalidad_rel',
    )

    class Meta:
        db_table = 'gen_documento_detalle'
        ordering = ['-id']
        verbose_name = 'Documento detalle'
        verbose_name_plural = 'Documentos detalles'

    def __str__(self):
        return f'{self.documento_id} - {self.id}'

    def calcular(self):
        cantidad = Decimal(str(self.cantidad or 0))
        precio = self.precio or Decimal('0')
        porcentaje = self.porcentaje_descuento or Decimal('0')

        self.subtotal = cantidad * precio
        self.descuento = (self.subtotal * porcentaje / Decimal('100')).quantize(Decimal('0.000001'))
        self.total_bruto = self.subtotal - self.descuento
        self.base_impuesto = self.total_bruto
        self.impuesto = Decimal('0')
        self.impuesto_retencion = Decimal('0')
        self.total = self.total_bruto + self.impuesto - self.impuesto_retencion
