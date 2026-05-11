from django.db import models


class GenCiudad(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    latitud = models.CharField(max_length=20, null=True)
    longitud = models.CharField(max_length=20, null=True)
    codigo_postal = models.CharField(max_length=10, null=True)
    porcentaje_impuesto = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    codigo = models.CharField(max_length=10, null=True)
    estado = models.ForeignKey('general.GenEstado', on_delete=models.PROTECT)

    class Meta:
        db_table = 'gen_ciudad'
        ordering = ['nombre']
        verbose_name = 'Ciudad'
        verbose_name_plural = 'Ciudades'

    def __str__(self):
        return self.nombre
