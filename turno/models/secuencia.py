from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TurSecuencia(models.Model):
    """
    Secuencia de turnos repetitiva, reutilizable al programar.

    Cada ranura (`dia_1`..`dia_31` y los días de la semana) guarda el `codigo`
    de un `TurTurno`. Al aplicar la secuencia sobre una programación se resuelve
    el turno por ese código. Un valor vacío/NULL significa "sin turno" (descanso).
    """

    nombre = models.CharField(max_length=60, null=True)
    codigo = models.CharField(max_length=10, unique=True)

    # Ranuras por día del mes (guardan el codigo de un TurTurno)
    dia_1 = models.CharField(max_length=10, null=True)
    dia_2 = models.CharField(max_length=10, null=True)
    dia_3 = models.CharField(max_length=10, null=True)
    dia_4 = models.CharField(max_length=10, null=True)
    dia_5 = models.CharField(max_length=10, null=True)
    dia_6 = models.CharField(max_length=10, null=True)
    dia_7 = models.CharField(max_length=10, null=True)
    dia_8 = models.CharField(max_length=10, null=True)
    dia_9 = models.CharField(max_length=10, null=True)
    dia_10 = models.CharField(max_length=10, null=True)
    dia_11 = models.CharField(max_length=10, null=True)
    dia_12 = models.CharField(max_length=10, null=True)
    dia_13 = models.CharField(max_length=10, null=True)
    dia_14 = models.CharField(max_length=10, null=True)
    dia_15 = models.CharField(max_length=10, null=True)
    dia_16 = models.CharField(max_length=10, null=True)
    dia_17 = models.CharField(max_length=10, null=True)
    dia_18 = models.CharField(max_length=10, null=True)
    dia_19 = models.CharField(max_length=10, null=True)
    dia_20 = models.CharField(max_length=10, null=True)
    dia_21 = models.CharField(max_length=10, null=True)
    dia_22 = models.CharField(max_length=10, null=True)
    dia_23 = models.CharField(max_length=10, null=True)
    dia_24 = models.CharField(max_length=10, null=True)
    dia_25 = models.CharField(max_length=10, null=True)
    dia_26 = models.CharField(max_length=10, null=True)
    dia_27 = models.CharField(max_length=10, null=True)
    dia_28 = models.CharField(max_length=10, null=True)
    dia_29 = models.CharField(max_length=10, null=True)
    dia_30 = models.CharField(max_length=10, null=True)
    dia_31 = models.CharField(max_length=10, null=True)

    # Ranuras por día de la semana / condición (guardan el codigo de un TurTurno)
    lunes = models.CharField(max_length=10, null=True)
    martes = models.CharField(max_length=10, null=True)
    miercoles = models.CharField(max_length=10, null=True)
    jueves = models.CharField(max_length=10, null=True)
    viernes = models.CharField(max_length=10, null=True)
    sabado = models.CharField(max_length=10, null=True)
    domingo = models.CharField(max_length=10, null=True)
    festivo = models.CharField(max_length=10, null=True)
    domingo_festivo = models.CharField(max_length=10, null=True)

    horas = models.IntegerField(default=0, db_default=0)
    dias = models.IntegerField(
        default=0,
        db_default=0,
        validators=[MinValueValidator(0), MaxValueValidator(31)],
    )
    homologar = models.BooleanField(default=False, db_default=False)
    estado_inactivo = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'tur_secuencia'
        ordering = ['nombre']
        verbose_name = 'Secuencia'
        verbose_name_plural = 'Secuencias'

    def __str__(self):
        return self.nombre or self.codigo
