from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum


class GenDocumento(models.Model):
    log_auditoria = True

    numero = models.IntegerField(null=True)
    fecha = models.DateField(null=True)
    fecha_contable = models.DateField(null=True)
    fecha_vence = models.DateField(null=True)
    fecha_validacion = models.DateTimeField(null=True)
    fecha_desde = models.DateField(null=True)
    fecha_hasta = models.DateField(null=True)
    subtotal = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total_bruto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_impuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    descuento = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    impuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    impuesto_retencion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    impuesto_operado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    afectado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pendiente = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pago = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    guias = models.IntegerField(default=0, db_default=0)
    dias = models.BigIntegerField(default=0, db_default=0)
    horas = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    horas_diurnas = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    horas_nocturnas = models.DecimalField(max_digits=10, decimal_places=2, default=0, db_default=0)
    salario = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    devengado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    deduccion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    provision_cesantia = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    provision_interes = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    provision_prima = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    provision_vacacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_prestacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_prestacion_vacacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    evento_documento = models.CharField(max_length=2, default='PE', db_default='PE')
    evento_recepcion = models.CharField(max_length=2, default='PE', db_default='PE')
    evento_aceptacion = models.CharField(max_length=2, default='PE', db_default='PE')
    estado_aprobado = models.BooleanField(default=False, db_default=False)
    estado_anulado = models.BooleanField(default=False, db_default=False)
    estado_contabilizado = models.BooleanField(default=False, db_default=False)
    estado_electronico = models.BooleanField(default=False, db_default=False)
    estado_electronico_enviado = models.BooleanField(default=False, db_default=False)
    estado_electronico_notificado = models.BooleanField(default=False, db_default=False)
    estado_electronico_evento = models.BooleanField(default=False, db_default=False)
    estado_electronico_descartado = models.BooleanField(default=False, db_default=False)
    soporte = models.CharField(max_length=100, null=True)
    orden_compra = models.CharField(max_length=50, null=True)
    remision = models.CharField(max_length=50, null=True)
    cue = models.CharField(max_length=150, null=True)
    comentario = models.CharField(max_length=500, null=True)
    qr = models.CharField(max_length=500, null=True)
    electronico_id = models.IntegerField(null=True)
    referencia_cue = models.CharField(max_length=150, null=True)
    referencia_numero = models.IntegerField(null=True)
    referencia_prefijo = models.CharField(max_length=50, null=True)
    documento_tipo = models.ForeignKey(
        'general.GenDocumentoTipo',
        on_delete=models.PROTECT,
        related_name='documentos_documento_tipo_rel',
    )
    contacto = models.ForeignKey(
        'general.GenContacto',
        null=True,
        on_delete=models.PROTECT,
        related_name='contactos_rel',
    )
    resolucion = models.ForeignKey(
        'general.GenResolucion',
        null=True,
        on_delete=models.PROTECT,
        related_name='gen_documentos',
    )
    documento_referencia = models.ForeignKey(
        'self',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_documento_referencia_rel',
    )
    plazo_pago = models.ForeignKey(
        'general.GenPlazoPago',
        null=True,
        on_delete=models.PROTECT,
        related_name='gen_documentos_plazo_pago_rel',
    )
    metodo_pago = models.ForeignKey(
        'general.GenMetodoPago',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_metodo_pago_rel',
    )
    asesor = models.ForeignKey(
        'general.GenAsesor',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_asesor_rel',
    )
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_usuario_rel',
    )
    cuenta_banco = models.ForeignKey(
        'general.GenCuentaBanco',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_cuenta_banco_rel',
    )
    comprobante = models.ForeignKey(
        'contabilidad.ConComprobante',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_comprobante_rel',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_cuenta_rel',
    )
    sector = models.ForeignKey(
        'general.GenSector',
        null=True,
        on_delete=models.PROTECT,
        related_name='documentos_sector_rel',
    )
    estrato = models.PositiveSmallIntegerField(
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(9)],
    )

    class Meta:
        db_table = 'gen_documento'
        ordering = ['-fecha', '-numero']
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'

    def __str__(self):
        return f'{self.documento_tipo_id} - {self.numero}'

    def es_mutable(self):
        return not (
            self.estado_aprobado
            or self.estado_anulado
            or self.estado_contabilizado
            or self.estado_electronico_enviado
        )

    def recalcular_totales(self):
        agregados = self.documentos_detalles_documento_rel.aggregate(
            subtotal=Sum('subtotal'),
            descuento=Sum('descuento'),
            total_bruto=Sum('total_bruto'),
            base_impuesto=Sum('base_impuesto'),
            impuesto=Sum('impuesto'),
            impuesto_retencion=Sum('impuesto_retencion'),
            total=Sum('total'),
            horas=Sum('horas'),
            horas_diurnas=Sum('horas_diurnas'),
            horas_nocturnas=Sum('horas_nocturnas'),
        )
        cero = Decimal('0')
        self.subtotal = agregados['subtotal'] or cero
        self.descuento = agregados['descuento'] or cero
        self.total_bruto = agregados['total_bruto'] or cero
        self.base_impuesto = agregados['base_impuesto'] or cero
        self.impuesto = agregados['impuesto'] or cero
        self.impuesto_retencion = agregados['impuesto_retencion'] or cero
        self.total = agregados['total'] or cero
        self.horas = agregados['horas'] or cero
        self.horas_diurnas = agregados['horas_diurnas'] or cero
        self.horas_nocturnas = agregados['horas_nocturnas'] or cero
