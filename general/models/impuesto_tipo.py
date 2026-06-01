from django.db import models


class GenImpuestoTipo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=10)
    nombre = models.CharField(max_length=20)

    class Meta:
        db_table = 'gen_impuesto_tipo'
        ordering = ['id']
        verbose_name = 'Tipo de impuesto'
        verbose_name_plural = 'Tipos de impuesto'

    def __str__(self):
        return self.nombre
