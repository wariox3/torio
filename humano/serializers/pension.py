from rest_framework import serializers

from humano.models import HumPension


class HumPensionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumPension
        fields = ['id', 'nombre', 'porcentaje_empleado', 'porcentaje_empleador', 'concepto']
