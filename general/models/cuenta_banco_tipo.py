from django.db import models


class GenCuentaBancoTipo(models.Model):
    nombre = models.CharField(max_length=100)

    class Meta:
        db_table = 'gen_cuenta_banco_tipo'
        ordering = ['nombre']
        verbose_name = 'Tipo de cuenta bancaria'
        verbose_name_plural = 'Tipos de cuenta bancaria'

    def __str__(self):
        return self.nombre
