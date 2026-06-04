from rest_framework import serializers

from humano.models import HumSalud


class HumSaludSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumSalud
        fields = ['id', 'nombre', 'porcentaje_empleado', 'concepto']
