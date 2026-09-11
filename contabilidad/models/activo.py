from decimal import Decimal

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
    centro_costo = models.ForeignKey(
        'contabilidad.ConCentroCosto', on_delete=models.PROTECT,
        related_name='activos_centro_costo_rel',
    )

    class Meta:
        db_table = 'con_activo'
        ordering = ['-id']
        verbose_name = 'Activo'
        verbose_name_plural = 'Activos'

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'

    def calcular_depreciacion(self):
        """
        Deriva del valor de compra la cuota del periodo y el saldo por depreciar.

        La duración está en meses, así que la cuota de línea recta es el valor de
        compra repartido en esos meses. El activo sin duración no deprecia: su
        cuota queda en cero en vez de reventar la división.

        El saldo es lo que le falta por depreciar: lo que costó, menos lo que ya
        venía depreciado cuando entró al sistema (`depreciacion_inicial`) y menos
        lo que se le ha depreciado acá (`depreciacion_acumulada`). Por eso el
        cálculo sirve igual al crear —donde lo acumulado es cero— que al editar,
        sin devolverle al activo un saldo que ya se gastó.

        No va en `save()` a propósito: lo llama quien captura el activo (el POST,
        el PATCH y el importador), no cualquiera que guarde el registro por otra
        razón.
        """
        duracion = self.duracion or 0
        if duracion > 0:
            self.depreciacion_periodo = round(self.valor_compra / duracion, 6)
        else:
            self.depreciacion_periodo = Decimal('0')
        self.depreciacion_saldo = (
            self.valor_compra - self.depreciacion_inicial - self.depreciacion_acumulada
        )
