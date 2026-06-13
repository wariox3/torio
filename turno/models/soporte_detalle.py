from django.db import models


class TurSoporteDetalle(models.Model):
    horas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_descansos = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_diurnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_nocturnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_festivas_diurnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_festivas_nocturnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_extras_diurnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_extras_nocturnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_extras_festivas_diurnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_extras_festivas_nocturnas = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_recargos_nocturnos = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_recargos_festivos_diurnos = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    horas_recargos_festivos_nocturnos = models.DecimalField(max_digits=10, decimal_places=3, default=0, db_default=0)
    soporte = models.ForeignKey(
        'turno.TurSoporte',
        on_delete=models.PROTECT,
        related_name='soportes_detalles_soporte_rel',
    )
    contrato = models.ForeignKey(
        'humano.HumContrato',
        on_delete=models.PROTECT,
        related_name='soportes_detalles_contrato_rel',
    )

    class Meta:
        db_table = 'tur_soporte_detalle'
        ordering = ['-id']
        verbose_name = 'Soporte detalle'
        verbose_name_plural = 'Soportes detalles'

    def __str__(self):
        return f'{self.id} - {self.contrato_id}'
