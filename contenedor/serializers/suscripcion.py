from rest_framework import serializers

from contenedor.models import CtnSuscripcion


class CtnSuscripcionSerializer(serializers.ModelSerializer):
    suscripcion_tipo_nombre = serializers.CharField(source='suscripcion_tipo.nombre', read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    usuario_nombre = serializers.CharField(source='usuario.username', read_only=True)

    class Meta:
        model = CtnSuscripcion
        fields = [
            'id',
            'cliente',
            'cliente_nombre',
            'usuario',
            'usuario_nombre',
            'suscripcion_tipo',
            'suscripcion_tipo_nombre',
            'fecha_inicio',
            'fecha_fin',
        ]
        read_only_fields = ['id']
