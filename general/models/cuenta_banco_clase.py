from django.db import models


class GenCuentaBancoClase(models.Model):
    nombre = models.CharField(max_length=30)

    class Meta:
        db_table = 'gen_cuenta_banco_clase'
        ordering = ['nombre']
        verbose_name = 'Clase de cuenta bancaria'
        verbose_name_plural = 'Clases de cuenta bancaria'

    def __str__(self):
        return self.nombre
