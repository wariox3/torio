from django.db import models


class ConCuentaCuenta(models.Model):
    id = models.IntegerField(primary_key=True)
    nombre = models.CharField(max_length=100, null=True)

    class Meta:
        db_table = 'con_cuenta_cuenta'
        ordering = ['id']
        verbose_name = 'Cuenta contable'
        verbose_name_plural = 'Cuentas contables'

    def __str__(self):
        return self.nombre or str(self.id)
