from django.db import models


class CtnContacto(models.Model):
    numero_identificacion = models.CharField(max_length=20)
    digito_verificacion = models.CharField(max_length=1, null=True)
    nombre_corto = models.CharField(max_length=200)
    direccion = models.CharField(max_length=50)
    telefono = models.CharField(max_length=50)
    correo = models.EmailField(max_length=255)
    identificacion = models.ForeignKey(
        'contenedor.CtnIdentificacion',
        on_delete=models.PROTECT,
        related_name='contactos',
    )
    ciudad = models.ForeignKey(
        'contenedor.CtnCiudad',
        on_delete=models.PROTECT,
        related_name='contactos',
    )
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.PROTECT,
        related_name='contactos',
    )

    class Meta:
        db_table = 'ctn_contacto'
        verbose_name = 'Contacto'
        verbose_name_plural = 'Contactos'
