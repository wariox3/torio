from django.db import models


class CtnAplicacion(models.Model):
    """Las aplicaciones (módulos) de torio: venta, compra, contabilidad, humano..."""

    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100)

    class Meta:
        db_table = 'ctn_aplicacion'
        ordering = ['id']
        verbose_name = 'Aplicación'
        verbose_name_plural = 'Aplicaciones'

    def __str__(self):
        return self.nombre
