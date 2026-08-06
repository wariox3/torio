from django.contrib.auth.models import Group, Permission
from rest_framework import serializers

from seguridad.models import SegUsuarioCliente


class SegGrupoUsuarioSerializer(serializers.Serializer):
    """
    Cuerpo para agregar o quitar un grupo a un usuario del contenedor.

    Opera sobre `permissions_usertenantpermissions_groups`.
    """

    usuario_id = serializers.IntegerField()
    grupo_id = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        source='grupo',
    )


class SegPermisoUsuarioSerializer(serializers.Serializer):
    """
    Cuerpo para agregar o quitar un permiso individual a un usuario del
    contenedor.

    Opera sobre `permissions_usertenantpermissions_user_permissions`, que es el
    permiso concedido directamente a la persona, al margen de sus grupos.
    """

    usuario_id = serializers.IntegerField()
    permiso_id = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
        source='permiso',
    )


class SegPermisoTenantSerializer(serializers.Serializer):
    """Solo para documentación del schema: el bloque `permiso` de la respuesta."""

    id = serializers.IntegerField(help_text='id de permissions_usertenantpermissions')
    profile_id = serializers.IntegerField(help_text='id de SegUsuario')
    is_superuser = serializers.BooleanField()
    is_staff = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    modified_at = serializers.DateTimeField()
    grupos = serializers.ListField(help_text='de permissions_usertenantpermissions_groups')
    permisos = serializers.ListField(help_text='de permissions_usertenantpermissions_user_permissions')


class SegUsuarioClientePermisoSerializer(serializers.ModelSerializer):
    """
    Miembro del contenedor con su fila de permisos.

    La membresía vive en el schema público y los permisos en el del tenant, así
    que no hay JOIN posible entre ambos. La vista arma un mapa
    {profile_id: UserTenantPermissions} y lo pasa por el contexto; acá solo se
    formatea.
    """

    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True)
    usuario_email = serializers.CharField(source='usuario.email', read_only=True)
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)
    permiso = serializers.SerializerMethodField()

    class Meta:
        model = SegUsuarioCliente
        fields = [
            'id',
            'usuario_id',
            'usuario_nombre_corto',
            'usuario_email',
            'rol_id',
            'rol_nombre',
            'permiso',
        ]
        read_only_fields = fields

    def get_permiso(self, obj):
        fila = (self.context.get('permisos') or {}).get(obj.usuario_id)
        if fila is None:
            # Miembro sin fila de permisos: la membresía se creó sin pasar por
            # `CtnCliente.add_user`. No tiene ningún permiso en el contenedor.
            return None

        return {
            'id': fila.id,
            'profile_id': fila.profile_id,
            'is_superuser': fila.is_superuser,
            'is_staff': fila.is_staff,
            'created_at': fila.created_at,
            'modified_at': fila.modified_at,
            'grupos': [{'id': g.id, 'nombre': g.name} for g in fila.groups.all()],
            'permisos': [
                {
                    'id': p.id,
                    'app': p.content_type.app_label,
                    'modelo': p.content_type.model,
                    'codename': p.codename,
                }
                for p in fila.user_permissions.all()
            ],
        }
