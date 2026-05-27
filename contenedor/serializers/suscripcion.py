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
            'frecuencia',
            'precio',
        ]
        read_only_fields = ['id', 'precio']

    def validate(self, attrs):
        suscripcion_tipo = attrs.get('suscripcion_tipo') or getattr(self.instance, 'suscripcion_tipo', None)
        frecuencia = attrs.get('frecuencia') or getattr(self.instance, 'frecuencia', None)
        if suscripcion_tipo is None or frecuencia is None:
            return attrs

        if suscripcion_tipo.suscripcion_categoria_id == 99:
            if frecuencia != CtnSuscripcion.FRECUENCIA_PRUEBA:
                raise serializers.ValidationError(
                    {'frecuencia': 'Para categoría 99 la frecuencia debe ser P (Prueba).'}
                )
        else:
            if frecuencia not in (CtnSuscripcion.FRECUENCIA_MENSUAL, CtnSuscripcion.FRECUENCIA_ANUAL):
                raise serializers.ValidationError(
                    {'frecuencia': 'La frecuencia debe ser M (Mensual) o A (Anual).'}
                )
        return attrs
