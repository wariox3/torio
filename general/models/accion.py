from django.db import models


class GenAccion(models.Model):
    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=50)

    class Meta:
        db_table = 'gen_accion'
        ordering = ['id']
        verbose_name = 'Acción'
        verbose_name_plural = 'Acciones'

    def __str__(self):
        return self.nombre
