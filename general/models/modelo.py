from django.db import models


class GenModelo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    app = models.CharField(max_length=50)
    clase = models.CharField(max_length=50)
    nombre = models.CharField(max_length=100)
    tabla = models.CharField(max_length=100, null=True)

    class Meta:
        db_table = 'gen_modelo'
        ordering = ['app', 'nombre']
        verbose_name = 'Modelo'
        verbose_name_plural = 'Modelos'

    def __str__(self):
        return f'{self.app}.{self.clase}'
