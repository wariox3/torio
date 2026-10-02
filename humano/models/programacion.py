import calendar
from datetime import timedelta

from django.db import models

from utilidades.fechas import dias_prestacionales


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

    @staticmethod
    def calcular_periodo(fecha_desde, fecha_hasta):
        """
        Los campos que se derivan de las fechas: no los manda el usuario.

        - `fecha_hasta_periodo`: el último día real del periodo. Una programación
          que se paga hasta el 30 de un mes de 31 días cierra el periodo el 31.
        - `dias_reales`: días calendario entre las fechas, ambas incluidas.
        - `dias`: días en la convención 30/360, los que se liquidan.
        """
        fecha_hasta_periodo = fecha_hasta
        if fecha_hasta.day == 30 and calendar.monthrange(fecha_hasta.year, fecha_hasta.month)[1] == 31:
            fecha_hasta_periodo = fecha_hasta + timedelta(days=1)
        return {
            'fecha_hasta_periodo': fecha_hasta_periodo,
            'dias_reales': (fecha_hasta - fecha_desde).days + 1,
            'dias': dias_prestacionales(fecha_desde, fecha_hasta),
        }

    def __str__(self):
        return self.nombre or str(self.id)
