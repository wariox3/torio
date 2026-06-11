from django.db import models


class GenFestivo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    fecha = models.DateField(unique=True)
    nombre = models.CharField(max_length=100, null=True)

    class Meta:
        db_table = 'gen_festivo'
        ordering = ['fecha']
        verbose_name = 'Festivo'
        verbose_name_plural = 'Festivos'

    def __str__(self):
        return f'{self.fecha} - {self.nombre or ""}'
