from django.db import models


class HumProgramacionDetalle(models.Model):
    fecha_desde = models.DateField(null=True)
    fecha_hasta = models.DateField(null=True)
    dias = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    dias_transporte = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    dias_novedad = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    salario = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    salario_promedio = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    base_prestacion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    diurna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    nocturna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    festiva_diurna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    festiva_nocturna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    extra_diurna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    extra_nocturna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    extra_festiva_diurna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    extra_festiva_nocturna = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    recargo_nocturno = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    recargo_festivo_diurno = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    recargo_festivo_nocturno = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    pago_horas = models.BooleanField(default=True, db_default=True)
    pago_auxilio_transporte = models.BooleanField(default=True, db_default=True)
    pago_incapacidad = models.BooleanField(default=True, db_default=True)
    pago_licencia = models.BooleanField(default=True, db_default=True)
    pago_vacacion = models.BooleanField(default=True, db_default=True)
    descuento_salud = models.BooleanField(default=True, db_default=True)
    descuento_pension = models.BooleanField(default=True, db_default=True)
    descuento_fondo_solidaridad = models.BooleanField(default=True, db_default=True)
    descuento_retencion_fuente = models.BooleanField(default=True, db_default=True)
    descuento_credito = models.BooleanField(default=True, db_default=True)
    descuento_embargo = models.BooleanField(default=True, db_default=True)
    adicional = models.BooleanField(default=True, db_default=True)
    ingreso = models.BooleanField(default=False, db_default=False)
    retiro = models.BooleanField(default=False, db_default=False)
    error_terminacion = models.BooleanField(default=False, db_default=False)
    base_cotizacion_acumulado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    devengado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    deduccion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    deduccion_fondo_pension_acumulado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    prima_propuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    cesantia_propuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    interes_propuesto = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    programacion = models.ForeignKey(
        'humano.HumProgramacion', on_delete=models.PROTECT,
        related_name='pogramaciones_detalles_programacion_rel',
    )
    contrato = models.ForeignKey(
        'humano.HumContrato', on_delete=models.PROTECT,
        related_name='pogramaciones_detalles_contrato_rel',
    )

    class Meta:
        db_table = 'hum_programacion_detalle'
        ordering = ['-id']
        verbose_name = 'Programación detalle'
        verbose_name_plural = 'Programaciones detalles'

    def __str__(self):
        return f'{self.id} - {self.contrato_id}'
