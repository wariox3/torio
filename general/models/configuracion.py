from django.db import models


class GenConfiguracion(models.Model):
    id = models.BigIntegerField(primary_key=True, default=1, db_default=1)
    gen_uvt = models.DecimalField(
        max_digits=20, decimal_places=6, default=0, db_default=0,
    )
    hum_factor = models.DecimalField(
        max_digits=6, decimal_places=3, default=0, db_default=0,
    )
    hum_salario_minimo = models.DecimalField(
        max_digits=20, decimal_places=6, default=0, db_default=0,
    )
    hum_auxilio_transporte = models.DecimalField(
        max_digits=20, decimal_places=6, default=0, db_default=0,
    )
    hum_entidad_riesgo = models.ForeignKey(
        'humano.HumEntidad', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_entidad_riesgo_rel',
    )
    gen_empresa_numero_identificacion = models.CharField(max_length=20, null=True)
    gen_empresa_digito_verificacion = models.CharField(max_length=1, null=True)
    gen_empresa_nombre_corto = models.CharField(max_length=200, default='', db_default='')
    gen_empresa_direccion = models.CharField(max_length=50, null=True)
    gen_empresa_telefono = models.CharField(max_length=50, null=True)
    gen_empresa_correo = models.EmailField(max_length=255, default='', db_default='')
    gen_empresa_imagen = models.TextField(null=True)
    gen_empresa_identificacion = models.ForeignKey(
        'general.GenIdentificacion', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_empresa_identificacion_rel',
    )
    gen_empresa_ciudad = models.ForeignKey(
        'general.GenCiudad', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_empresa_ciudad_rel',
    )
    gen_empresa_tipo_persona = models.ForeignKey(
        'general.GenTipoPersona', null=True, on_delete=models.PROTECT,
        related_name='configuraciones_empresa_tipo_persona_rel',
    )

    class Meta:
        db_table = 'gen_configuracion'
        verbose_name = 'Configuración'
        verbose_name_plural = 'Configuraciones'

    def __str__(self):
        return 'Configuración'
