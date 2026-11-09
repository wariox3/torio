from django.db import models


class ConExogenaFormato(models.Model):
    """Catálogo de los formatos de información exógena de la DIAN.

    El id es el número del formato (1001, 1003…), así que los ids de
    `catalogos/09_exogena_formato.json` no pueden cambiar.

    `cuantia_menor` es el tope por tercero bajo el cual el valor no se reporta
    con el tercero sino acumulado en el NIT 222222222. Lo fija la resolución de
    cada año gravable; en cero, todo se reporta por tercero.
    """

    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=200)
    cuantia_menor = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)

    class Meta:
        db_table = 'con_exogena_formato'
        ordering = ['id']
        verbose_name = 'Formato de exógena'
        verbose_name_plural = 'Formatos de exógena'

    def __str__(self):
        return f'{self.id} - {self.nombre}'
