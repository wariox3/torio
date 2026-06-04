from django.db import models


class HumContrato(models.Model):
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    salario = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    auxilio_transporte = models.BooleanField(default=False, db_default=False)
    salario_integral = models.BooleanField(default=False, db_default=False)
    estado_terminado = models.BooleanField(default=False, db_default=False)
    comentario = models.CharField(max_length=300, null=True)
    fecha_ultimo_pago = models.DateField(null=True)
    fecha_ultimo_pago_prima = models.DateField(null=True)
    fecha_ultimo_pago_cesantia = models.DateField(null=True)
    fecha_ultimo_pago_vacacion = models.DateField(null=True)
    contrato_tipo = models.ForeignKey(
        'humano.HumContratoTipo', on_delete=models.PROTECT,
        related_name='contratos_contrato_tipo_rel',
    )
    contacto = models.ForeignKey(
        'general.GenContacto', on_delete=models.PROTECT,
        related_name='contratos_contacto_rel',
    )
    ciudad_contrato = models.ForeignKey(
        'general.GenCiudad', null=True, on_delete=models.PROTECT,
        related_name='contratos_ciudad_contrato_rel',
    )
    ciudad_labora = models.ForeignKey(
        'general.GenCiudad', null=True, on_delete=models.PROTECT,
        related_name='contratos_ciudad_labora_rel',
    )
    grupo = models.ForeignKey(
        'humano.HumGrupo', on_delete=models.PROTECT,
        related_name='contratos_grupo_rel',
    )
    sucursal = models.ForeignKey(
        'humano.HumSucursal', null=True, on_delete=models.PROTECT,
        related_name='contratos_sucursal_rel',
    )
    riesgo = models.ForeignKey(
        'humano.HumRiesgo', null=True, on_delete=models.PROTECT,
        related_name='contratos_riesgo_rel',
    )
    tipo_cotizante = models.ForeignKey(
        'humano.HumTipoCotizante', null=True, on_delete=models.PROTECT,
        related_name='contratos_tipo_cotizante_rel',
    )
    subtipo_cotizante = models.ForeignKey(
        'humano.HumSubtipoCotizante', null=True, on_delete=models.PROTECT,
        related_name='contratos_subtipo_cotizante_rel',
    )
    cargo = models.ForeignKey(
        'humano.HumCargo', null=True, on_delete=models.PROTECT,
        related_name='contratos_cargo_rel',
    )
    salud = models.ForeignKey(
        'humano.HumSalud', null=True, on_delete=models.PROTECT,
        related_name='contratos_salud_rel',
    )
    pension = models.ForeignKey(
        'humano.HumPension', null=True, on_delete=models.PROTECT,
        related_name='contratos_pension_rel',
    )
    entidad_salud = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='contratos_entidad_salud_rel',
    )
    entidad_pension = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='contratos_entidad_pension_rel',
    )
    entidad_cesantias = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='contratos_entidad_cesantias_rel',
    )
    entidad_caja = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='contratos_entidad_caja_rel',
    )
    tiempo = models.ForeignKey(
        'humano.HumTiempo', null=True, on_delete=models.PROTECT,
        related_name='contratos_tiempo_rel',
    )
    tipo_costo = models.ForeignKey(
        'humano.HumTipoCosto', null=True, on_delete=models.PROTECT,
        related_name='contratos_tipo_costo_rel',
    )
    grupo_contabilidad = models.ForeignKey(
        'contabilidad.ConCentroCosto', null=True, on_delete=models.PROTECT,
        related_name='contratos_grupo_contabilidad_rel',
    )
    motivo_terminacion = models.ForeignKey(
        'humano.HumMotivoTerminacion', null=True, on_delete=models.PROTECT,
        related_name='contratos_motivo_terminacion_rel',
    )

    class Meta:
        db_table = 'hum_contrato'
        ordering = ['-id']
        verbose_name = 'Contrato'
        verbose_name_plural = 'Contratos'

    def __str__(self):
        return f'{self.id} - {self.contacto_id}'
