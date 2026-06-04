from django.db import models


class ConConciliacion(models.Model):
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    cuenta_banco = models.ForeignKey(
        'general.GenCuentaBanco', null=True, on_delete=models.PROTECT,
        related_name='conciliaciones_cuenta_banco_rel',
    )

    class Meta:
        db_table = 'con_conciliacion'
        ordering = ['-id']
        verbose_name = 'Conciliación'
        verbose_name_plural = 'Conciliaciones'

    def __str__(self):
        return str(self.id)
