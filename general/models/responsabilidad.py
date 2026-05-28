from django.db import models


class GenResponsabilidad(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=10, null=True)
    estado_activo = models.BooleanField(default=True, db_default=True)
    orden = models.BigIntegerField(default=0, db_default=0)

    class Meta:
        db_table = 'gen_responsabilidad'
        ordering = ['orden', 'nombre']
        verbose_name = 'Responsabilidad'
        verbose_name_plural = 'Responsabilidades'

    def __str__(self):
        return self.nombre
