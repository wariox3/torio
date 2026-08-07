from django.db import models

# Aplicaciones que el front muestra en el menú del contenedor. Es el orden en el
# que se declaran los flags `acceso_*` acá y en `CtnInvitacion`, y lo que
# recorren los serializers e `CtnCliente.add_user` para copiarlos.
#
# No autoriza nada: quien autoriza es el grupo (ver `seguridad.grupos`). Estos
# flags solo dicen qué módulos ve el usuario dentro del contenedor.
CAMPOS_ACCESO = (
    'acceso_venta',
    'acceso_compra',
    'acceso_tesoreria',
    'acceso_cartera',
    'acceso_inventario',
    'acceso_humano',
    'acceso_contabilidad',
    'acceso_turno',
)


class SegUsuarioCliente(models.Model):
    usuario = models.ForeignKey(
        'seguridad.SegUsuario',
        on_delete=models.CASCADE,
        db_column='usuario_id',
        related_name='membresias',
    )
    cliente = models.ForeignKey(
        'contenedor.CtnCliente',
        on_delete=models.CASCADE,
        db_column='cliente_id',
    )
    rol = models.ForeignKey(
        'seguridad.SegRol',
        null=True,
        on_delete=models.SET_NULL,
        related_name='membresias',
    )
    # Arrancan en False: el acceso a cada módulo se concede explícitamente al
    # invitar, no se hereda por ser miembro del contenedor.
    acceso_venta = models.BooleanField(default=False, db_default=False)
    acceso_compra = models.BooleanField(default=False, db_default=False)
    acceso_tesoreria = models.BooleanField(default=False, db_default=False)
    acceso_cartera = models.BooleanField(default=False, db_default=False)
    acceso_inventario = models.BooleanField(default=False, db_default=False)
    acceso_humano = models.BooleanField(default=False, db_default=False)
    acceso_contabilidad = models.BooleanField(default=False, db_default=False)
    acceso_turno = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'seg_usuario_cliente'
        verbose_name = 'Usuario-Cliente'
        verbose_name_plural = 'Usuario-Clientes'
        unique_together = [['usuario', 'cliente']]
