from django.db import models


class CtnModelo(models.Model):
    """
    Los modelos del schema público, al estilo de `GenModelo` en el tenant. Le da a
    las funcionalidades genéricas del master (como los adjuntos de `CtnArchivo`) un
    id estable con el que referirse a cualquier modelo sin una FK propia.

    Los ids son manuales y fijos en `catalogos/07_modelo.json`, iguales en todos los
    ambientes. Van seguidos desde 1: a diferencia del tenant, acá no hay rangos por
    app. Se agrega una fila cuando una funcionalidad la necesita.
    """

    class Tipo(models.TextChoices):
        ADMINISTRADOR = 'A', 'Administrador'
        MOVIMIENTO = 'M', 'Movimiento'
        DETALLE = 'D', 'Detalle'
        CATALOGO = 'C', 'Catálogo'
        SOPORTE = 'S', 'Soporte'

    id = models.BigIntegerField(primary_key=True)
    app = models.CharField(max_length=50)
    clase = models.CharField(max_length=50)
    nombre = models.CharField(max_length=100)
    tabla = models.CharField(max_length=100, null=True)
    tipo = models.CharField(
        max_length=1,
        choices=Tipo.choices,
        default=Tipo.ADMINISTRADOR,
        db_default=Tipo.ADMINISTRADOR,
    )

    class Meta:
        db_table = 'ctn_modelo'
        ordering = ['app', 'nombre']
        verbose_name = 'Modelo'
        verbose_name_plural = 'Modelos'

    def __str__(self):
        return f'{self.app}.{self.clase}'
