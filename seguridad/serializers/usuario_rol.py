from rest_framework import serializers

from seguridad.models import SegUsuarioRol


class SegUsuarioRolSerializer(serializers.ModelSerializer):
    usuario_email = serializers.CharField(source='usuario.email', read_only=True)
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)
    tenant_nombre = serializers.CharField(source='tenant.nombre', read_only=True)

    class Meta:
        model = SegUsuarioRol
        fields = [
            'id', 'usuario', 'rol', 'tenant',
            'usuario_email', 'rol_nombre', 'tenant_nombre',
            'fecha_asignacion',
        ]
        read_only_fields = ['id', 'fecha_asignacion']
