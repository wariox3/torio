from django.db import models


class GenConfiguracionUsuario(models.Model):
    """
    Las preferencias de un usuario dentro de este contenedor: una fila por usuario.

    Son valores **por defecto** que el front propone (al crear un documento, al
    abrir el POS…); no limitan nada, el usuario puede escoger otro. Solo los edita
    el propio usuario, por `/general/configuracion-usuario/`.

    `usuario_id` es el `SegUsuario.pk` sin FK, como en `GenLog`: la cuenta vive en
    el esquema público y ningún modelo del tenant le pone FK. Si el usuario sale
    del contenedor la fila se queda, y la recupera si vuelve.

    Los FK van con `SET_NULL`: borrar la sede, el almacén o la caja solo le quita
    el valor por defecto a quien lo tenía.
    """

    usuario_id = models.BigIntegerField(unique=True)
    sede = models.ForeignKey(
        'general.GenSede',
        null=True,
        on_delete=models.SET_NULL,
        related_name='configuraciones_usuario_sede_rel',
    )
    almacen = models.ForeignKey(
        'inventario.InvAlmacen',
        null=True,
        on_delete=models.SET_NULL,
        related_name='configuraciones_usuario_almacen_rel',
    )
    caja = models.ForeignKey(
        'venta.VenCaja',
        null=True,
        on_delete=models.SET_NULL,
        related_name='configuraciones_usuario_caja_rel',
    )

    class Meta:
        db_table = 'gen_configuracion_usuario'
        verbose_name = 'Configuración de usuario'
        verbose_name_plural = 'Configuraciones de usuario'

    def __str__(self):
        return f'Configuración del usuario {self.usuario_id}'
