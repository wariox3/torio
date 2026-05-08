from django.db import models


class CtnEstado(models.Model):
    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=50)
    codigo = models.CharField(max_length=10, null=True)
    pais = models.ForeignKey(
        'contenedor.CtnPais',
        on_delete=models.CASCADE,
        related_name='estados',
    )

    class Meta:
        db_table = 'ctn_estado'
        verbose_name = 'Estado'
        verbose_name_plural = 'Estados'

    def __str__(self):
        return self.nombre
