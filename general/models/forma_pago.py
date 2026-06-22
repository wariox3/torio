from django.db import models


class GenFormaPago(models.Model):
    nombre = models.CharField(max_length=50)
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta', null=True, on_delete=models.PROTECT,
        related_name='formas_pagos_cuenta_rel',
    )

    class Meta:
        db_table = 'gen_forma_pago'
        ordering = ['id']
        verbose_name = 'Forma de pago'
        verbose_name_plural = 'Formas de pago'

    def __str__(self):
        return self.nombre
