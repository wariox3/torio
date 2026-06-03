from django.db import models


class TurProgramador(models.Model):
    nombre = models.CharField(max_length=100)
    estado_inactivo = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'tur_programador'
        ordering = ['nombre']
        verbose_name = 'Programador'
        verbose_name_plural = 'Programadores'

    def __str__(self):
        return self.nombre
