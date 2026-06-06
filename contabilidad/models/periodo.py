from django.db import models


class ConPeriodo(models.Model):
    anio = models.BigIntegerField()
    mes = models.BigIntegerField()
    estado_bloqueado = models.BooleanField(default=False, db_default=False)
    estado_cerrado = models.BooleanField(default=False, db_default=False)
    estado_inconsistencia = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'con_periodo'
        ordering = ['-id']
        unique_together = ('anio', 'mes')
        verbose_name = 'Periodo'
        verbose_name_plural = 'Periodos'

    def __str__(self):
        return f'{self.anio}-{self.mes:02d}'
