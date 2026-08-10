from django.db import models


class GenModelo(models.Model):
    class Tipo(models.TextChoices):
        ADMINISTRADOR = 'A', 'Administrador'
        MOVIMIENTO = 'M', 'Movimiento'
        DETALLE = 'D', 'Detalle'
        FIXTURE = 'F', 'Fixture'
        SOPORTE = 'S', 'Soporte'

    # Tipos cuyo acceso se decide con permisos de modelo. Su viewset declara
    # `TienePermisoModelo` y `/general/modelo/<id>/permiso/` devuelve el resultado real
    # de `has_perm`, que es lo que el front usa para pintar los botones.
    #
    # Los demás quedan fuera por razones distintas:
    #   - FIXTURE y DETALLE: catálogos compartidos, o filas que se manejan a través de su
    #     documento padre.
    #   - SOPORTE: funcionalidades verticales, que atraviesan los módulos y no se
    #     restringen por rol. Un adjunto lo usa quien esté trabajando el documento, sin
    #     un permiso propio.
    #
    # Las dos listas tienen que coincidir: si un tipo está acá, su viewset declara la
    # permission class, y si no está, no la declara. Al revés el front esconde botones
    # que la API sí acepta, o los muestra y la API responde 403.
    TIPOS_CON_PERMISO = (Tipo.ADMINISTRADOR, Tipo.MOVIMIENTO)

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
        db_table = 'gen_modelo'
        ordering = ['app', 'nombre']
        verbose_name = 'Modelo'
        verbose_name_plural = 'Modelos'

    def __str__(self):
        return f'{self.app}.{self.clase}'
