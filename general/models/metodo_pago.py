from django.db import models


class GenMetodoPago(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=10, null=True)

    class Meta:
        db_table = 'gen_metodo_pago'
        ordering = ['nombre']
        verbose_name = 'Método de pago'
        verbose_name_plural = 'Métodos de pago'

    def __str__(self):
        return self.nombre
