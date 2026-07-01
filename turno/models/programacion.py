from django.db import models


class TurProgramacion(models.Model):
    fecha = models.DateField()
    horas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    horas_diurnas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    horas_nocturnas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    festivo = models.BooleanField(default=False, db_default=False)
    contrato = models.ForeignKey(
        'humano.HumContrato',
        on_delete=models.PROTECT,
        related_name='programaciones_contrato_rel',
    )
    documento_detalle = models.ForeignKey(
        'general.GenDocumentoDetalle',
        on_delete=models.PROTECT,
        related_name='programaciones_documento_detalle_rel',
    )
    turno = models.ForeignKey(
        'turno.TurTurno',
        on_delete=models.PROTECT,
        related_name='programaciones_turno_rel',
    )

    class Meta:
        db_table = 'tur_programacion'
        ordering = ['fecha', 'id']
        verbose_name = 'Programación'
        verbose_name_plural = 'Programaciones'
        constraints = [
            models.UniqueConstraint(
                fields=['contrato', 'fecha'],
                name='uniq_programacion_contrato_fecha',
            ),
        ]

    def __str__(self):
        return f'{self.contrato_id} - {self.fecha}'
