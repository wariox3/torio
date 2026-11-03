from rest_framework import serializers

from seguridad.models import SegUsuarioCliente


class SegUsuarioClienteSerializer(serializers.ModelSerializer):
    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True)
    usuario_email = serializers.CharField(source='usuario.email', read_only=True)
    # Ids de los grupos (`auth.Group`) de esta membresía: sus permisos en el
    # contenedor, y con ellos el menú. Con `is_superuser` tiene todos.
    grupos = serializers.SlugRelatedField(
        slug_field='grupo_id', many=True, read_only=True,
    )

    class Meta:
        model = SegUsuarioCliente
        fields = [
            'id',
            'usuario_id',
            'usuario_nombre_corto',
            'usuario_email',
            'cliente_id',
            'propietario',
            'soporte',
            'is_superuser',
            'grupos',
        ]
        read_only_fields = ['id', 'soporte', 'is_superuser']
