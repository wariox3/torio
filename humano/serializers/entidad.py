from rest_framework import serializers

from humano.models import HumEntidad


class HumEntidadSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumEntidad
        fields = [
            'id', 'codigo', 'numero_identificacion', 'nombre', 'nombre_extendido',
            'salud', 'pension', 'cesantias', 'caja', 'riesgo', 'sena', 'icbf',
        ]
