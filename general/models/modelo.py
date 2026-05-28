from django.db import models


class GenModelo(models.Model):
    class Tipo(models.TextChoices):
        ADMINISTRADOR = 'A', 'Administrador'
        MOVIMIENTO = 'M', 'Movimiento'
        DETALLE = 'D', 'Detalle'

    id = models.BigIntegerField(primary_key=True)
    app = models.CharField(max_length=50)
    clase = models.CharField(max_length=50)
    nombre = models.CharField(max_length=100)
    tabla = models.CharField(max_length=100, null=True)
    tipo = models.CharField(
        max_length=1,
        choices=Tipo.choices,
        default=Tipo.ADMINISTRADOR,
        db_default=Tipo.ADMINISTRADOR,
    )

    class Meta:
        db_table = 'gen_modelo'
        ordering = ['app', 'nombre']
        verbose_name = 'Modelo'
        verbose_name_plural = 'Modelos'

    def __str__(self):
        return f'{self.app}.{self.clase}'
