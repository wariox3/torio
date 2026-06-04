from django.db import models


class HumConfiguracionAporte(models.Model):
    id = models.BigIntegerField(primary_key=True)
    tipo = models.CharField(max_length=20, null=True)
    orden = models.IntegerField(default=0, db_default=0)
    cuenta = models.ForeignKey(
        'contabilidad.ConCuenta', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_aportes_cuenta_rel',
    )

    class Meta:
        db_table = 'hum_configuracion_aporte'
        ordering = ['orden']
        verbose_name = 'Configuración aporte'
        verbose_name_plural = 'Configuraciones aportes'

    def __str__(self):
        return self.tipo or ''
