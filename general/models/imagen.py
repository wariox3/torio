import uuid as uuid_lib

from django.db import models


class GenImagen(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    objeto_id = models.CharField(max_length=50, db_index=True)
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, db_index=True)
    principal = models.BooleanField(default=False, db_default=False)
    modelo = models.ForeignKey('general.GenModelo', on_delete=models.PROTECT)

    class Meta:
        db_table = 'gen_imagen'
        ordering = ['-principal', '-id']
        indexes = [models.Index(fields=['modelo', 'objeto_id'])]
        constraints = [
            # Una sola principal por registro. La garantiza la base y no solo el
            # servicio: dos subidas simultáneas al mismo registro vacío verían
            # cada una "todavía no hay principal".
            models.UniqueConstraint(
                fields=['modelo', 'objeto_id'],
                condition=models.Q(principal=True),
                name='gen_imagen_una_principal',
            ),
        ]
        verbose_name = 'Imagen'
        verbose_name_plural = 'Imágenes'

    def __str__(self):
        return str(self.uuid)
