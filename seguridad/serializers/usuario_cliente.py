from rest_framework import serializers

from seguridad.models import SegUsuarioCliente


class SegUsuarioClienteSerializer(serializers.ModelSerializer):
    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True)
    usuario_email = serializers.CharField(source='usuario.email', read_only=True)
    rol_nombre = serializers.CharField(source='rol.nombre', read_only=True)

    class Meta:
        model = SegUsuarioCliente
        fields = [
            'id',
            'usuario_id',
            'usuario_nombre_corto',
            'usuario_email',
            'cliente_id',
            'rol_id',
            'rol_nombre',
            'acceso_venta',
            'acceso_compra',
            'acceso_tesoreria',
            'acceso_cartera',
            'acceso_inventario',
            'acceso_humano',
            'acceso_contabilidad',
        ]
        read_only_fields = ['id']
