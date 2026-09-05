from django.db import models


class GenDocumentoPago(models.Model):
    """
    Cada pago aplicado a un documento contra una cuenta bancaria.

    Un documento puede recibir varios pagos, y cada uno se contabiliza contra la
    cuenta de su propia cuenta bancaria, así que el pago no cabe como un campo
    del documento.
    """

    pago = models.DecimalField(max_digits=20, decimal_places=6, default=0, db_default=0)
    estado_anulado = models.BooleanField(default=False, db_default=False)
    documento = models.ForeignKey(
        'general.GenDocumento',
        on_delete=models.PROTECT,
        related_name='documentos_pagos_documento',
    )
    cuenta_banco = models.ForeignKey(
        'general.GenCuentaBanco',
        on_delete=models.PROTECT,
        related_name='documentos_pagos_cuenta_banco',
    )

    class Meta:
        db_table = 'gen_documento_pago'
        ordering = ['-id']
        verbose_name = 'Documento pago'
        verbose_name_plural = 'Documentos pagos'

    def __str__(self):
        return f'{self.documento_id} - {self.pago}'
