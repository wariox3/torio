from django.db import models


class HumConfiguracionProvision(models.Model):
    id = models.BigIntegerField(primary_key=True)
    tipo = models.CharField(max_length=20, null=True)
    orden = models.IntegerField(default=0, db_default=0)
    tipo_costo = models.ForeignKey(
        'humano.HumTipoCosto', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_provisiones_tipo_costo_rel',
    )
    cuenta_debito = models.ForeignKey(
        'contabilidad.ConCuenta', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_provisiones_cuenta_debito_rel',
    )
    cuenta_credito = models.ForeignKey(
        'contabilidad.ConCuenta', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_provisiones_cuenta_credito_rel',
    )

    class Meta:
        db_table = 'hum_configuracion_provision'
        ordering = ['orden']
        verbose_name = 'Configuración provisión'
        verbose_name_plural = 'Configuraciones provisiones'

    def __str__(self):
        return self.tipo or ''
