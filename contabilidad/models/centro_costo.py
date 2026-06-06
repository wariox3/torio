from django.db import models


class ConCentroCosto(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, unique=True, null=True)

    class Meta:
        db_table = 'con_centro_costo'
        ordering = ['codigo']
        verbose_name = 'Centro de costo'
        verbose_name_plural = 'Centros de costo'

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'
