from django.db import models


class GenEstado(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    codigo = models.CharField(max_length=10, null=True)
    pais = models.ForeignKey('general.GenPais', on_delete=models.PROTECT)

    class Meta:
        db_table = 'gen_estado'
        ordering = ['-id']
        verbose_name = 'Estado'
        verbose_name_plural = 'Estados'

    def __str__(self):
        return self.nombre
