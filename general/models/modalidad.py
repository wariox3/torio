from django.db import models


class GenModalidad(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100, null=True)
    codigo = models.CharField(max_length=10, null=True)
    porcentaje_comercial = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)
    porcentaje_residencial = models.DecimalField(max_digits=5, decimal_places=2, default=0, db_default=0)

    class Meta:
        db_table = 'gen_modalidad'
        ordering = ['nombre']
        verbose_name = 'Modalidad'
        verbose_name_plural = 'Modalidades'

    def __str__(self):
        return self.nombre or ''
