from django.db import models


class GenTipoPersona(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=30)

    class Meta:
        db_table = 'gen_tipo_persona'
        ordering = ['nombre']
        verbose_name = 'Tipo de persona'
        verbose_name_plural = 'Tipos de persona'

    def __str__(self):
        return self.nombre
