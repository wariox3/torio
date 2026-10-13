from django.db import models


class GenDocumentoElectronicoError(models.Model):
    """
    Un motivo por el que un documento no se pudo emitir electrónicamente.

    Un documento puede fallar por varias cosas a la vez —sin resolución y con el
    proveedor sin código postal—, así que no caben en un campo. Solo se guardan los
    del último intento: cada emisión borra los anteriores, y si sale bien no queda
    ninguno. `GenDocumento.estado_electronico_error` dice si hay alguno.
    """

    class Fase(models.TextChoices):
        # Lo que torio revisa antes de enviar: no salió nada hacia rededoc.
        VALIDACION = 'validacion', 'Validación'
        # Rededoc recibió el documento y lo rechazó.
        EMISION = 'emision', 'Emisión'

    fase = models.CharField(max_length=20, choices=Fase.choices)
    mensaje = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)
    documento = models.ForeignKey(
        'general.GenDocumento',
        on_delete=models.CASCADE,
        related_name='documentos_electronicos_errores_documento_rel',
    )

    class Meta:
        db_table = 'gen_documento_electronico_error'
        ordering = ['id']
        verbose_name = 'Documento electrónico error'
        verbose_name_plural = 'Documentos electrónicos errores'

    def __str__(self):
        return f'{self.documento_id} - {self.mensaje[:60]}'
