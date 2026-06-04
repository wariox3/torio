from django.db import models


class HumEntidad(models.Model):
    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=20)
    numero_identificacion = models.CharField(max_length=20)
    nombre = models.CharField(max_length=200)
    nombre_extendido = models.CharField(max_length=200, null=True)
    salud = models.BooleanField(default=False, db_default=False)
    pension = models.BooleanField(default=False, db_default=False)
    cesantias = models.BooleanField(default=False, db_default=False)
    caja = models.BooleanField(default=False, db_default=False)
    riesgo = models.BooleanField(default=False, db_default=False)
    sena = models.BooleanField(default=False, db_default=False)
    icbf = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'hum_entidad'
        ordering = ['nombre']
        verbose_name = 'Entidad'
        verbose_name_plural = 'Entidades'

    def __str__(self):
        return self.nombre
