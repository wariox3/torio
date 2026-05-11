from django.db import models


class GenCuentaBanco(models.Model):
    nombre = models.CharField(max_length=100)
    numero_cuenta = models.CharField(max_length=50, null=True)
    cuenta_banco_tipo = models.ForeignKey(
        'general.GenCuentaBancoTipo', on_delete=models.PROTECT,
        related_name='cuentas_bancos_cuenta_banco_tipo',
    )
    cuenta_banco_clase = models.ForeignKey(
        'general.GenCuentaBancoClase', null=True, on_delete=models.PROTECT,
        related_name='cuentas_bancos_cuenta_banco_clase',
    )
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta', null=True, on_delete=models.PROTECT,
        related_name='cuentas_bancos_cuenta_rel',
    )

    class Meta:
        db_table = 'gen_cuenta_banco'
        ordering = ['nombre']
        verbose_name = 'Cuenta bancaria'
        verbose_name_plural = 'Cuentas bancarias'

    def __str__(self):
        return self.nombre
