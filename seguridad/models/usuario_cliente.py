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
    # Dueño del contenedor; va siempre a la par de `CtnCliente.owner`. Tiene todos
    # los permisos (`SegUsuario.has_perm`) y es el único que transfiere la
    # propiedad y elimina el contenedor (`es_propietario`).
    #
    # Las tres marcas —`propietario`, `administrador`, `soporte`— dan todos los
    # permisos dentro del contenedor; un miembro sin ninguna tiene los de sus
    # grupos (`SegUsuarioClienteGrupo`) y sus permisos personalizados. Viven acá,
    # y no en `UserTenantPermissions`, para leerlas sin entrar al schema.
    propietario = models.BooleanField(default=False, db_default=False)
    # Tiene todo lo del dueño —todos los permisos y `es_superusuario`— salvo
    # transferir la propiedad y eliminar el contenedor (`es_propietario`). Nunca
    # junto con `propietario` ni `soporte`.
    administrador = models.BooleanField(default=False, db_default=False)
    # Staff de la plataforma que entró a dar soporte (`POST /contenedor/cliente/<id>/soporte/`).
    # Tiene todos los permisos en el tenant, pero no es un usuario del cliente:
    # no administra ni elimina el contenedor (`es_superusuario`). Dura hasta que se cierra —él se sale o el owner lo
    # saca, con el mismo `DELETE` de cualquier membresía— y al cerrarse no queda rastro.
    soporte = models.BooleanField(default=False, db_default=False)

    class Meta:
        db_table = 'seg_usuario_cliente'
        verbose_name = 'Usuario-Cliente'
        verbose_name_plural = 'Usuario-Clientes'
        unique_together = [['usuario', 'cliente']]
