from django.db import models


class GenPais(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50, null=True)
    codigo = models.CharField(max_length=10, null=True)
    estado_inactivo = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'gen_pais'
        ordering = ['-id']
        verbose_name = 'País'
        verbose_name_plural = 'Países'

    def __str__(self):
        return self.nombre or self.id
