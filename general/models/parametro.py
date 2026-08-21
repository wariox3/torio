from django.db import models


class GenParametro(models.Model):
    id = models.BigIntegerField(primary_key=True, default=1, db_default=1)
    gen_factura_electronica_activa = models.BooleanField(default=False, db_default=False)
    gen_factura_electronica_emisor = models.BigIntegerField(null=True)
    # La escribe `servicios.factura_electronica.cargar_certificado` con lo que
    # responde rededoc. Es una copia informativa: el dueño del certificado es
    # rededoc, así que esta fecha sirve para mostrar y avisar, no para decidir
    # si el tenant puede facturar. `null` significa que nunca se cargó uno.
    gen_certificado_vence = models.DateField(null=True)

    class Meta:
        db_table = 'gen_parametro'
        verbose_name = 'Parámetro'
        verbose_name_plural = 'Parámetros'

    def __str__(self):
        return 'Parámetro'
