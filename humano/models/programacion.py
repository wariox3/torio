from django.db import models


class HumProgramacion(models.Model):
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    fecha_hasta_periodo = models.DateField()
    nombre = models.CharField(max_length=100, null=True)
    dias = models.IntegerField(default=0, db_default=0)
    dias_reales = models.IntegerField(default=0, db_default=0)
    contratos = models.IntegerField(default=0, db_default=0)
    devengado = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    deduccion = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    total = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    estado_aprobado = models.BooleanField(default=False, db_default=False)
    estado_generado = models.BooleanField(default=False, db_default=False)
    pago_horas = models.BooleanField(default=True, db_default=True)
    pago_auxilio_transporte = models.BooleanField(default=True, db_default=True)
    pago_incapacidad = models.BooleanField(default=True, db_default=True)
    pago_licencia = models.BooleanField(default=True, db_default=True)
    pago_vacacion = models.BooleanField(default=True, db_default=True)
    pago_prima = models.BooleanField(default=True, db_default=True)
    pago_cesantia = models.BooleanField(default=True, db_default=True)
    pago_interes = models.BooleanField(default=True, db_default=True)
    descuento_salud = models.BooleanField(default=True, db_default=True)
    descuento_pension = models.BooleanField(default=True, db_default=True)
    descuento_fondo_solidaridad = models.BooleanField(default=True, db_default=True)
    descuento_retencion_fuente = models.BooleanField(default=True, db_default=True)
    descuento_credito = models.BooleanField(default=True, db_default=True)
    descuento_embargo = models.BooleanField(default=True, db_default=True)
    adicional = models.BooleanField(default=True, db_default=True)
    comentario = models.CharField(max_length=300, null=True)
    base_prestacion_minimo = models.BooleanField(default=False, db_default=False)
    base_prestacion_minimo_salario = models.BooleanField(default=True, db_default=True)
    grupo = models.ForeignKey(
        'humano.HumGrupo', on_delete=models.PROTECT,
        related_name='pogramaciones_grupo_rel',
    )
    pago_tipo = models.ForeignKey(
        'humano.HumPagoTipo', on_delete=models.PROTECT,
        related_name='pogramaciones_pago_tipo_rel',
    )
    periodo = models.ForeignKey(
        'humano.HumPeriodo', null=True, on_delete=models.PROTECT,
        related_name='programaciones_periodo_rel',
    )

    class Meta:
        db_table = 'hum_programacion'
        ordering = ['-id']
        verbose_name = 'Programación'
        verbose_name_plural = 'Programaciones'

    def __str__(self):
        return self.nombre or str(self.id)
