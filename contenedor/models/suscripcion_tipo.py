from django.db import models


class CtnSuscripcionTipo(models.Model):
    id = models.IntegerField(primary_key=True)
    nombre = models.CharField(max_length=100)
    precio = models.DecimalField(max_digits=14, decimal_places=2)
    suscripcion_clase_id = models.BigIntegerField(null=True)
    suscripcion_categoria_id = models.BigIntegerField(null=True)

    class Meta:
        db_table = 'ctn_suscripcion_tipo'
        verbose_name = 'Tipo de suscripción'
        verbose_name_plural = 'Tipos de suscripción'

    def __str__(self):
        return self.nombre
