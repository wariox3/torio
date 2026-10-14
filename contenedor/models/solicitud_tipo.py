from django.db import models


class CtnSolicitudTipo(models.Model):
    """Qué se le pide a torio en una `CtnSolicitud` (por ahora, el certificado de firma)."""

    id = models.BigIntegerField(primary_key=True)
    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=100)

    class Meta:
        db_table = 'ctn_solicitud_tipo'
        ordering = ['id']
        verbose_name = 'Tipo de solicitud'
        verbose_name_plural = 'Tipos de solicitud'

    def __str__(self):
        return self.nombre
