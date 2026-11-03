from rest_framework import serializers

from contenedor import imagen as imagen_servicio
from seguridad.models import SegUsuarioCliente


class SegUsuarioClienteSerializer(serializers.ModelSerializer):
    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True)
    usuario_email = serializers.CharField(source='usuario.email', read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True, allow_null=True)
    cliente_schema_name = serializers.CharField(
        source='cliente.schema_name', read_only=True, allow_null=True,
    )
    cliente_imagen_thumbnail = serializers.SerializerMethodField()
    # El efectivo: el propietario tiene todo aunque su fila no lo marque.
    is_superuser = serializers.SerializerMethodField()
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
            'cliente_nombre',
            'cliente_schema_name',
            'cliente_imagen_thumbnail',
            'propietario',
            'soporte',
            'is_superuser',
            'grupos',
        ]
        read_only_fields = ['id', 'soporte', 'is_superuser']

    def get_is_superuser(self, obj) -> bool:
        return obj.is_superuser or obj.propietario

    def get_cliente_imagen_thumbnail(self, obj) -> str | None:
        return imagen_servicio.url_thumbnail(obj.cliente)
