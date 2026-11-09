from django.db import models


class ConExogena(models.Model):
    """La información exógena de un año gravable: una por año y por tenant.

    Los formatos que la empresa presenta ese año son sus detalles
    (`ConExogenaDetalle`). Presentada, ni ella ni sus detalles se modifican.
    """

    anio = models.IntegerField(unique=True)
    comentario = models.CharField(max_length=500, null=True)
    estado_generado = models.BooleanField(default=False, db_default=False)
    estado_presentado = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'con_exogena'
        ordering = ['-anio']
        verbose_name = 'Exógena'
        verbose_name_plural = 'Exógenas'

    def __str__(self):
        return str(self.anio)
