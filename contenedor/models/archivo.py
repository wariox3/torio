import uuid as uuid_lib

from django.db import models


class CtnArchivo(models.Model):
    """
    Adjunto de cualquier modelo del schema público, como `GenArchivo` en el tenant:
    `modelo` (`CtnModelo`) + `objeto_id` dicen de qué registro es.

    Lleva además `cliente`, que `GenArchivo` no necesita: en el tenant el schema es
    la frontera, y acá todos los clientes comparten tabla. Es lo que decide quién lo
    ve (los miembros de ese contenedor) y dónde queda en B2. No lo manda el front:
    `contenedor.servicios.archivo.subir` lo toma del registro dueño.

    Los archivos perduran: no hay retención ni borrado.
    """

    fecha = models.DateTimeField(auto_now_add=True)
    objeto_id = models.CharField(max_length=50)
    nombre = models.CharField(max_length=500)
    tipo = models.CharField(max_length=100)
    tamano = models.BigIntegerField(default=0, db_default=0)
    almacenamiento_id = models.CharField(max_length=500)
    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True)
    # SET_NULL y no PROTECT ni CASCADE: el archivo sobrevive al contenedor (y a su
    # objeto en B2), y eliminar un contenedor no se puede trabar por sus adjuntos.
    cliente = models.ForeignKey(
        'contenedor.CtnCliente',
        null=True,
        on_delete=models.SET_NULL,
        related_name='archivos',
    )
    modelo = models.ForeignKey('contenedor.CtnModelo', on_delete=models.PROTECT)
    archivo_tipo = models.ForeignKey('contenedor.CtnArchivoTipo', on_delete=models.PROTECT)

    class Meta:
        db_table = 'ctn_archivo'
        ordering = ['-id']
        indexes = [models.Index(fields=['modelo', 'objeto_id'])]
        verbose_name = 'Archivo'
        verbose_name_plural = 'Archivos'

    def __str__(self):
        return self.nombre
