from django.db import models


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
    # Dueño del contenedor. Es la contraparte por membresía de `CtnCliente.owner`,
    # que es un dato informativo y nulable. NO autoriza: quien autoriza son los
    # grupos (`SegUsuarioClienteGrupo`) y el salto de `TienePermisoModelo` lo da
    # `is_superuser`, los dos de esta membresía.
    propietario = models.BooleanField(default=False, db_default=False)
    # Staff de la plataforma que entró a dar soporte (`POST /contenedor/cliente/<id>/soporte/`).
    # Es una membresía con `is_superuser` en el tenant, pero no es un usuario del
    # cliente: no puede modificar ni eliminar el contenedor (`es_superusuario`). Dura hasta que se cierra —él se sale o el owner lo
    # saca, con el mismo `DELETE` de cualquier membresía— y al cerrarse no queda rastro.
    soporte = models.BooleanField(default=False, db_default=False)
    # Todos los permisos dentro de este contenedor (`SegUsuario.has_perm`). Lo
    # tienen el dueño y el soporte. Vive acá, y no en `UserTenantPermissions`,
    # para poder leerlo sin entrar al schema del contenedor.
    is_superuser = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'seg_usuario_cliente'
        verbose_name = 'Usuario-Cliente'
        verbose_name_plural = 'Usuario-Clientes'
        unique_together = [['usuario', 'cliente']]
