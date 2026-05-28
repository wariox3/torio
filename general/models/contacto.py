from django.db import models


class GenContacto(models.Model):
    log_auditoria = True

    numero_identificacion = models.CharField(max_length=20)
    digito_verificacion = models.CharField(max_length=1, null=True)
    nombre_corto = models.CharField(max_length=200)
    nombre1 = models.CharField(max_length=50, null=True)
    nombre2 = models.CharField(max_length=50, null=True)
    apellido1 = models.CharField(max_length=50, null=True)
    apellido2 = models.CharField(max_length=50, null=True)
    direccion = models.CharField(max_length=100)
    barrio = models.CharField(max_length=200, null=True)
    codigo_ciuu = models.CharField(max_length=200, null=True)
    codigo_postal = models.CharField(max_length=20, null=True)
    telefono = models.CharField(max_length=50)
    celular = models.CharField(max_length=50, null=True)
    correo = models.CharField(max_length=255)
    correo_facturacion_electronica = models.CharField(max_length=255, null=True)
    cliente = models.BooleanField(default=False, db_default=False)
    proveedor = models.BooleanField(default=False, db_default=False)
    empleado = models.BooleanField(default=False, db_default=False)
    conductor = models.BooleanField(default=False, db_default=False)
    numero_cuenta = models.CharField(max_length=50, null=True)
    numero_licencia = models.CharField(max_length=50, null=True)
    fecha_vence_licencia = models.DateField(null=True)
    identificacion = models.ForeignKey(
        'general.GenIdentificacion', on_delete=models.PROTECT,
    )
    ciudad = models.ForeignKey(
        'general.GenCiudad', on_delete=models.PROTECT,
    )
    tipo_persona = models.ForeignKey(
        'general.GenTipoPersona', on_delete=models.PROTECT,
    )
    asesor = models.ForeignKey(
        'general.GenAsesor', null=True, on_delete=models.PROTECT,
    )
    precio = models.ForeignKey(
        'general.GenPrecio', null=True, on_delete=models.PROTECT,
    )
    plazo_pago = models.ForeignKey(
        'general.GenPlazoPago', null=True, on_delete=models.PROTECT,
        related_name='contactos_plazo_pago',
    )
    plazo_pago_proveedor = models.ForeignKey(
        'general.GenPlazoPago', null=True, on_delete=models.PROTECT,
        related_name='contactos_plazo_pago_proveedor',
    )
    banco = models.ForeignKey(
        'general.GenBanco', null=True, on_delete=models.PROTECT,
    )
    cuenta_banco_clase = models.ForeignKey(
        'general.GenCuentaBancoClase', null=True, on_delete=models.PROTECT,
    )

    class Meta:
        db_table = 'gen_contacto'
        verbose_name = 'Contacto'
        verbose_name_plural = 'Contactos'

    def __str__(self):
        return self.nombre_corto
