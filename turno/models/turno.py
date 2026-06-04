from django.db import models


class TurTurno(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=10, unique=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    horas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    horas_diurnas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    horas_nocturnas = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    color = models.CharField(max_length=7, null=True)
    estado_inactivo = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'tur_turno'
        ordering = ['nombre']
        verbose_name = 'Turno'
        verbose_name_plural = 'Turnos'

    def __str__(self):
        return self.nombre
