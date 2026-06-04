from rest_framework import serializers

from humano.models import HumRiesgo


class HumRiesgoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumRiesgo
        fields = ['id', 'codigo', 'nombre', 'porcentaje']
