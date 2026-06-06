from django.db import models


class ConCuenta(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=100)
    exige_base = models.BooleanField(default=False, db_default=False)
    exige_contacto = models.BooleanField(default=False, db_default=False)
    exige_grupo = models.BooleanField(default=False, db_default=False)
    permite_movimiento = models.BooleanField(default=False, db_default=False)
    nivel = models.IntegerField(null=True)
    cuenta_clase = models.ForeignKey(
        'contabilidad.ConCuentaClase', null=True, on_delete=models.PROTECT,
    )
    cuenta_grupo = models.ForeignKey(
        'contabilidad.ConCuentaGrupo', null=True, on_delete=models.PROTECT,
    )
    cuenta_cuenta = models.ForeignKey(
        'contabilidad.ConCuentaCuenta', null=True, on_delete=models.PROTECT,
    )
    cuenta_subcuenta = models.ForeignKey(
        'contabilidad.ConCuentaSubcuenta', null=True, on_delete=models.PROTECT,
    )

    class Meta:
        db_table = 'con_cuenta'
        ordering = ['codigo']
        verbose_name = 'Cuenta'
        verbose_name_plural = 'Cuentas'

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'
