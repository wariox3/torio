from django.db import models


class GenParametro(models.Model):
    id = models.BigIntegerField(primary_key=True, default=1, db_default=1)
    gen_factura_electronica_activa = models.BooleanField(default=False, db_default=False)
    gen_factura_electronica_emisor = models.BigIntegerField(null=True)
    # La escribe `servicios.factura_electronica.cargar_certificado` con lo que
    # responde rededoc. Es una copia informativa: el dueño del certificado es
    # rededoc, así que esta fecha sirve para mostrar y avisar, no para decidir
    # si el tenant puede facturar. `null` significa que nunca se cargó uno.
    gen_certificado_vence = models.DateField(null=True)
    # Asistente de datos iniciales: mientras esté en True el front ofrece cargar
    # una plantilla o descartarla. Arranca encendido y lo apaga el back —al aplicar
    # una plantilla o al descartar—, nunca un PATCH del front. El default importa:
    # `GenParametro` no tiene fixture y su fila la crea `SingletonMixin` al primer
    # acceso, así que un contenedor recién creado tiene que salir de ahí encendido.
    gen_asistente_datos_iniciales = models.BooleanField(default=True, db_default=True)

    class Meta:
        db_table = 'gen_parametro'
        verbose_name = 'Parámetro'
        verbose_name_plural = 'Parámetros'

    def __str__(self):
        return 'Parámetro'
