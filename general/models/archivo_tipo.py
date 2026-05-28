from django.db import models


class GenArchivoTipo(models.Model):
    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=50)

    class Meta:
        db_table = 'gen_archivo_tipo'
        ordering = ['id']
        verbose_name = 'Tipo de archivo'
        verbose_name_plural = 'Tipos de archivo'

    def __str__(self):
        return self.nombre
