from django.db import models


class TurProgramacionSimulacion(models.Model):
    fecha = models.DateField()
    horas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    horas_diurnas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    horas_nocturnas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    festivo = models.BooleanField(default=False, db_default=False)
    posicion = models.IntegerField(default=1, db_default=1)
    contrato = models.ForeignKey(
        'humano.HumContrato',
        null=True,
        on_delete=models.PROTECT,
        related_name='programaciones_simulacion_contrato_rel',
    )
    documento_detalle = models.ForeignKey(
        'general.GenDocumentoDetalle',
        null=True,
        on_delete=models.PROTECT,
        related_name='programaciones_simulacion_documento_detalle_rel',
    )
    turno = models.ForeignKey(
        'turno.TurTurno',
        null=True,
        on_delete=models.PROTECT,
        related_name='programaciones_simulacion_turno_rel',
    )

    class Meta:
        db_table = 'tur_programacion_simulacion'
        ordering = ['fecha', 'id']
        verbose_name = 'Programación simulación'
        verbose_name_plural = 'Programaciones simulación'

    def __str__(self):
        return f'{self.id} - {self.fecha}'
