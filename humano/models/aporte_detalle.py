from django.db import models


class HumAporteDetalle(models.Model):
    horas = models.IntegerField(default=0, db_default=0)
    dias_pension = models.IntegerField(default=0, db_default=0)
    dias_salud = models.IntegerField(default=0, db_default=0)
    dias_riesgos = models.IntegerField(default=0, db_default=0)
    dias_caja = models.IntegerField(default=0, db_default=0)
    dias_incapacidad_laboral = models.IntegerField(default=0, db_default=0)
    base_cotizacion_pension = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion_salud = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion_riesgos = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion_caja = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_cotizacion_otros_parafiscales = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    tarifa_pension = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    tarifa_salud = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    tarifa_riesgos = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    tarifa_caja = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    tarifa_sena = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    tarifa_icbf = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_pension = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_voluntario_pension_afiliado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_voluntario_pension_aportante = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_solidaridad_solidaridad = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_solidaridad_subsistencia = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total_cotizacion_pension = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_salud = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_riesgos = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_caja = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_sena = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_icbf = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cotizacion_total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    upc_adicional = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    fecha_ingreso = models.DateField(null=True)
    fecha_retiro = models.DateField(null=True)
    fecha_inicio_variacion_permanente_salario = models.DateField(null=True)
    fecha_inicio_suspension_temporal_contrato = models.DateField(null=True)
    fecha_fin_suspension_temporal_contrato = models.DateField(null=True)
    fecha_inicio_incapacidad_general = models.DateField(null=True)
    fecha_fin_incapacidad_general = models.DateField(null=True)
    fecha_inicio_licencia_maternidad = models.DateField(null=True)
    fecha_fin_licencia_maternidad = models.DateField(null=True)
    fecha_inicio_vacaciones = models.DateField(null=True)
    fecha_fin_vacaciones = models.DateField(null=True)
    fecha_inicio_incapacidad_laboral = models.DateField(null=True)
    fecha_fin_incapacidad_laboral = models.DateField(null=True)
    ingreso = models.BooleanField(default=False, db_default=False)
    retiro = models.BooleanField(default=False, db_default=False)
    variacion_permanente_salario = models.BooleanField(default=False, db_default=False)
    variacion_transitoria_salario = models.BooleanField(default=False, db_default=False)
    suspension_temporal_contrato = models.BooleanField(default=False, db_default=False)
    incapacidad_general = models.BooleanField(default=False, db_default=False)
    licencia_maternidad = models.BooleanField(default=False, db_default=False)
    vacaciones = models.BooleanField(default=False, db_default=False)
    licencia_remunerada = models.BooleanField(default=False, db_default=False)
    aporte_voluntario_pension = models.BooleanField(default=False, db_default=False)
    variacion_centro_trabajo = models.BooleanField(default=False, db_default=False)
    salario_integral = models.BooleanField(default=False, db_default=False)
    aporte_contrato = models.ForeignKey(
        'humano.HumAporteContrato', on_delete=models.PROTECT,
        related_name='aportes_detalles_aporte_contrato_rel',
    )

    class Meta:
        db_table = 'hum_aporte_detalle'
        ordering = ['-id']
        verbose_name = 'Aporte detalle'
        verbose_name_plural = 'Aportes detalles'

    def __str__(self):
        return str(self.id)
