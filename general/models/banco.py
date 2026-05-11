from django.db import models


class GenBanco(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    codigo = models.CharField(max_length=10, null=True)

    class Meta:
        db_table = 'gen_banco'
        ordering = ['nombre']
        verbose_name = 'Banco'
        verbose_name_plural = 'Bancos'

    def __str__(self):
        return self.nombre
