from django.db import models


class ConActivo(models.Model):
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=100)
    marca = models.CharField(max_length=100, null=True)
    serie = models.CharField(max_length=100, null=True)
    modelo = models.CharField(max_length=100, null=True)
    fecha_compra = models.DateField()
    fecha_activacion = models.DateField()
    fecha_baja = models.DateField(null=True)
    duracion = models.IntegerField(null=True)
    valor_compra = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    depreciacion_inicial = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    depreciacion_periodo = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    depreciacion_acumulada = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    depreciacion_saldo = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    activo_grupo = models.ForeignKey(
        'contabilidad.ConActivoGrupo', on_delete=models.PROTECT,
        related_name='activos_activo_grupo_rel',
    )
    metodo_depreciacion = models.ForeignKey(
        'contabilidad.ConMetodoDepreciacion', on_delete=models.PROTECT,
        related_name='activos_metodo_depreciacion_rel',
    )
    cuenta_gasto = models.ForeignKey(
        'contabilidad.ConCuenta', on_delete=models.PROTECT,
        related_name='activos_cuenta_gasto_rel',
    )
    cuenta_depreciacion = models.ForeignKey(
        'contabilidad.ConCuenta', on_delete=models.PROTECT,
        related_name='activos_cuenta_depreciacion_rel',
    )
    grupo = models.ForeignKey(
        'contabilidad.ConCentroCosto', on_delete=models.PROTECT,
        related_name='activos_grupo_rel',
    )

    class Meta:
        db_table = 'con_activo'
        ordering = ['-id']
        verbose_name = 'Activo'
        verbose_name_plural = 'Activos'

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'
