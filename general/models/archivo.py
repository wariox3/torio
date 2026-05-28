import uuid as uuid_lib

from django.db import models


class GenArchivo(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    archivo_tipo = models.ForeignKey(
        'general.GenArchivoTipo',
        on_delete=models.PROTECT,
        default=1,
        db_default=1,
    )
    modelo = models.ForeignKey('general.GenModelo', on_delete=models.PROTECT)
    objeto_id = models.CharField(max_length=50, db_index=True)
    nombre = models.CharField(max_length=500)
    tipo = models.CharField(max_length=100)
    tamano = models.BigIntegerField(default=0, db_default=0)
    almacenamiento_id = models.CharField(max_length=500)
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, db_index=True)
    url = models.CharField(max_length=500, null=True)

    class Meta:
        db_table = 'gen_archivo'
        ordering = ['-id']
        indexes = [models.Index(fields=['modelo', 'objeto_id'])]
        verbose_name = 'Archivo'
        verbose_name_plural = 'Archivos'

    def __str__(self):
        return self.nombre
