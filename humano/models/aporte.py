from django.db import models


class HumAporte(models.Model):
    fecha_desde = models.DateField(null=True)
    fecha_hasta = models.DateField(null=True)
    fecha_hasta_periodo = models.DateField(null=True)
    anio = models.BigIntegerField(default=0, db_default=0)
    anio_salud = models.BigIntegerField(default=0, db_default=0)
    mes = models.BigIntegerField(default=0, db_default=0)
    mes_salud = models.BigIntegerField(default=0, db_default=0)
    presentacion = models.CharField(max_length=1, default='S', db_default='S')
    contratos = models.IntegerField(default=0, db_default=0)
    empleados = models.IntegerField(default=0, db_default=0)
    lineas = models.IntegerField(default=0, db_default=0)
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
    estado_aprobado = models.BooleanField(default=False, db_default=False)
    estado_generado = models.BooleanField(default=False, db_default=False)
    comentario = models.CharField(max_length=300, null=True)
    sucursal = models.ForeignKey(
        'humano.HumSucursal', null=True, on_delete=models.PROTECT,
        related_name='aportes_sucursal_rel',
    )
    entidad_riesgo = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_entidad_riesgo_rel',
    )
    entidad_sena = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_entidad_sena_rel',
    )
    entidad_icbf = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='aportes_entidad_icbf_rel',
    )

    class Meta:
        db_table = 'hum_aporte'
        ordering = ['-id']
        verbose_name = 'Aporte'
        verbose_name_plural = 'Aportes'

    def __str__(self):
        return str(self.id)
