from rest_framework import serializers

from contenedor.models import CtnPendiente


class CtnPendienteSerializer(serializers.ModelSerializer):
    cliente_id = serializers.IntegerField(read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    pendiente_tipo_id = serializers.IntegerField(read_only=True)
    pendiente_tipo_nombre = serializers.CharField(source='pendiente_tipo.nombre', read_only=True)
    pendiente_tipo_aplicacion_id = serializers.IntegerField(
        source='pendiente_tipo.aplicacion_id', read_only=True,
    )
    pendiente_tipo_aplicacion_nombre = serializers.CharField(
        source='pendiente_tipo.aplicacion.nombre', read_only=True,
    )

    class Meta:
        model = CtnPendiente
        fields = [
            'id', 'fecha', 'mensaje', 'cantidad',
            'cliente_id', 'cliente_nombre',
            'pendiente_tipo_id', 'pendiente_tipo_nombre',
            'pendiente_tipo_aplicacion_id', 'pendiente_tipo_aplicacion_nombre',
        ]
        read_only_fields = fields
