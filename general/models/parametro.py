from django.db import models


class GenParametro(models.Model):
    """
    Estado que deja el uso de la aplicación, a diferencia de `GenConfiguracion`,
    que es lo que el usuario llena en la pantalla de ajustes.

    Acá no se guarda nada que el usuario edite por formulario: son consecuencias
    de sus decisiones (que ya se habilitó en un servicio, que ya completó un
    paso) y espejos de sistemas externos. Por eso no debe existir un `PATCH`
    genérico sobre este modelo: se lee completo y se escribe desde el flujo
    concreto que produce cada dato. Si el front pudiera escribirlo,
    `gen_factura_electronica_activa` dejaría de ser un hecho y pasaría a ser
    una afirmación del cliente.

    Fila única por tenant (`id=1`), igual que `GenConfiguracion`.
    """

    id = models.BigIntegerField(primary_key=True, default=1, db_default=1)
    # Lo dice el servicio de facturación electrónica, no el cliente: acá solo se
    # copia para que el front sepa si ofrecer o no la activación.
    gen_factura_electronica_activa = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'gen_parametro'
        verbose_name = 'Parámetro'
        verbose_name_plural = 'Parámetros'

    def __str__(self):
        return 'Parámetro'
