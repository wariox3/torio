from django.db import models


class HumNovedad(models.Model):
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    fecha_desde_periodo = models.DateField(null=True)
    fecha_hasta_periodo = models.DateField(null=True)
    fecha_desde_empresa = models.DateField(null=True)
    fecha_hasta_empresa = models.DateField(null=True)
    fecha_desde_entidad = models.DateField(null=True)
    fecha_hasta_entidad = models.DateField(null=True)
    dias_disfrutados = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    dias_disfrutados_reales = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    dias_dinero = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    pago_disfrute = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    dias = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    dias_empresa = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    dias_entidad = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    pago_dinero = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pago_dia_disfrute = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pago_dia_dinero = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion_propuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    hora_empresa = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    hora_entidad = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pago_empresa = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    pago_entidad = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    dias_acumulados = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    prorroga = models.BooleanField(default=False, db_default=False)
    detalle = models.CharField(max_length=150, null=True)
    contrato = models.ForeignKey(
        'humano.HumContrato', on_delete=models.PROTECT,
        related_name='novedades_contrato_rel',
    )
    novedad_tipo = models.ForeignKey(
        'humano.HumNovedadTipo', null=True, on_delete=models.PROTECT,
        related_name='novedades_novedad_tipo_rel',
    )
    novedad_referencia = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='novedades_novedad_referencia_rel',
    )

    class Meta:
        db_table = 'hum_novedad'
        ordering = ['-id']
        verbose_name = 'Novedad'
        verbose_name_plural = 'Novedades'

    def __str__(self):
        return f'{self.id} - {self.contrato_id}'
