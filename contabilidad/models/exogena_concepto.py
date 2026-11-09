from django.db import models


class ConExogenaConcepto(models.Model):
    """Catálogo de los conceptos de cada formato de exógena (5001 salarios, 5002 honorarios…).

    `codigo` es el que va en el archivo de la DIAN y es único dentro de su
    formato. El id es aparte para que un código que la resolución cambie de
    sentido de un año a otro pueda convivir con el anterior.
    """

    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=10)
    nombre = models.CharField(max_length=300)
    formato = models.ForeignKey(
        'contabilidad.ConExogenaFormato',
        on_delete=models.PROTECT,
        related_name='exogena_conceptos_formato_rel',
    )

    class Meta:
        db_table = 'con_exogena_concepto'
        ordering = ['formato_id', 'codigo']
        verbose_name = 'Concepto de exógena'
        verbose_name_plural = 'Conceptos de exógena'
        constraints = [
            models.UniqueConstraint(fields=['formato', 'codigo'], name='con_exogena_concepto_formato_codigo_uniq'),
        ]

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'
