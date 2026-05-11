from django.db import models


class ConCuentaSubcuenta(models.Model):
    id = models.IntegerField(primary_key=True)
    nombre = models.CharField(max_length=100, null=True)

    class Meta:
        db_table = 'con_cuenta_subcuenta'
        ordering = ['id']
        verbose_name = 'Subcuenta'
        verbose_name_plural = 'Subcuentas'

    def __str__(self):
        return self.nombre or str(self.id)
