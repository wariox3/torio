from django.db import models


class CtnDatosFacturacion(models.Model):
    numero_identificacion = models.CharField(max_length=20, null=True)
    digito_verificacion = models.CharField(max_length=1, null=True)
    nombre_corto = models.CharField(max_length=200)
    direccion = models.CharField(max_length=50, null=True)
    telefono = models.CharField(max_length=50, null=True)
    correo = models.EmailField(max_length=255)
    identificacion = models.ForeignKey(
        'contenedor.CtnIdentificacion',
        on_delete=models.PROTECT,
        related_name='datos_facturacion',
    )
    ciudad = models.ForeignKey(
        'contenedor.CtnCiudad',
        on_delete=models.PROTECT,
        related_name='datos_facturacion',
    )
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.PROTECT,
        related_name='datos_facturacion',
    )

    class Meta:
        db_table = 'ctn_datos_facturacion'
