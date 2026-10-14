from django.db import models


class GenDocumentoConceptoCorreccion(models.Model):
    """
    Por qué una nota corrige el documento que referencia. Es el concepto que la
    DIAN exige en las notas (`ResponseCode`), y cada clase de nota tiene su propia
    lista: los códigos se repiten entre ellas, por eso el concepto va atado a su
    clase y no se elige por código.
    """

    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=10)
    nombre = models.CharField(max_length=150)
    documento_clase = models.ForeignKey(
        'general.GenDocumentoClase',
        on_delete=models.PROTECT,
        related_name='documentos_conceptos_correccion_documento_clase_rel',
    )

    class Meta:
        db_table = 'gen_documento_concepto_correccion'
        ordering = ['id']
        verbose_name = 'Concepto de corrección'
        verbose_name_plural = 'Conceptos de corrección'

    def __str__(self):
        return self.nombre
