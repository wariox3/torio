from django.db import models


class ConInconsistenciaTipo(models.Model):
    """Catálogo de los tipos de inconsistencia que revisa `analizar_inconsistencias`.

    El servicio se refiere a cada tipo por su id (`servicios.movimiento.TIPO_*`),
    así que los ids de `catalogos/08_inconsistencia_tipo.json` no pueden cambiar.
    """

    id = models.BigIntegerField(primary_key=True)
    nombre = models.CharField(max_length=100)
    # El tipo se puede corregir sin intervención del usuario. Todavía ninguno lo
    # hace: el campo queda listo para cuando exista la corrección automática.
    resolver_automatico = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'con_inconsistencia_tipo'
        ordering = ['id']
        verbose_name = 'Tipo de inconsistencia'
        verbose_name_plural = 'Tipos de inconsistencia'

    def __str__(self):
        return self.nombre
