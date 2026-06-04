from django.db import models


class HumAporteContrato(models.Model):
    fecha_desde = models.DateField(null=True)
    fecha_hasta = models.DateField(null=True)
    dias = models.IntegerField(default=0, db_default=0)
    salario = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_pension = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_pension_total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_pension_empresa = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_pension_empleado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_voluntario_pension_afiliado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_voluntario_pension_aportante = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_solidaridad_solidaridad = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_solidaridad_subsistencia = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_salud = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_salud_empresa = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_salud_empleado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_riesgos = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_caja = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_sena = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_icbf = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    ingreso = models.BooleanField(default=False, db_default=False)
    retiro = models.BooleanField(default=False, db_default=False)
    error_terminacion = models.BooleanField(default=False, db_default=False)
    aporte = models.ForeignKey(
        'humano.HumAporte', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_aporte_rel',
    )
    contrato = models.ForeignKey(
        'humano.HumContrato', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_contrato_rel',
    )
    ciudad_labora = models.ForeignKey(
        'general.GenCiudad', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_ciudad_labora_rel',
    )
    entidad_salud = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_entidad_salud_rel',
    )
    entidad_pension = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_entidad_pension_rel',
    )
    entidad_caja = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_entidad_caja_rel',
    )
    entidad_riesgo = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_entidad_riesgo_rel',
    )
    entidad_sena = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_entidad_sena_rel',
    )
    entidad_icbf = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_entidad_icbf_rel',
    )
    riesgo = models.ForeignKey(
        'humano.HumRiesgo', null=True, on_delete=models.PROTECT,
        related_name='aportes_contratos_riesgo_rel',
    )

    class Meta:
        db_table = 'hum_aporte_contrato'
        ordering = ['-id']
        verbose_name = 'Aporte contrato'
        verbose_name_plural = 'Aportes contratos'

    def __str__(self):
        return f'{self.id} - {self.contrato_id}'
