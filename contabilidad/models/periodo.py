from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ConPeriodo(models.Model):
    # El id no es un consecutivo: es el propio periodo codificado como anio*100+mes
    # (202601 = enero de 2026). Así se le asigna periodo a una transacción con
    # aritmética sobre su fecha, sin consultar esta tabla, y `periodo_id` ya es
    # legible en un movimiento sin hacer JOIN. Depende de que `mes` esté acotado
    # a 1–13, o dos años distintos podrían codificar el mismo id.
    id = models.BigIntegerField(primary_key=True, editable=False)
    anio = models.BigIntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
    )
    # 1–12 son los meses; el 13 es el periodo de ajustes y cierre.
    mes = models.BigIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(13)],
    )
    estado_bloqueado = models.BooleanField(default=False, db_default=False)
    estado_cerrado = models.BooleanField(default=False, db_default=False)
    estado_inconsistencia = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'con_periodo'
        ordering = ['-id']
        unique_together = ('anio', 'mes')
        verbose_name = 'Periodo'
        verbose_name_plural = 'Periodos'

    @staticmethod
    def calcular_id(anio, mes):
        return anio * 100 + mes

    def save(self, *args, **kwargs):
        id_derivado = self.calcular_id(self.anio, self.mes)
        if self._state.adding:
            self.id = id_derivado
        elif id_derivado != self.id:
            # Cambiar anio o mes cambiaría la PK: sería otro periodo, y el UPDATE
            # dejaría el original en pie más una fila duplicada.
            raise ValueError('No se puede cambiar el año o el mes de un periodo existente')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.anio}-{self.mes:02d}'
