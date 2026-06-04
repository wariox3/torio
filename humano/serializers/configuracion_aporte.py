from rest_framework import serializers

from humano.models import HumConfiguracionAporte


class HumConfiguracionAporteSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumConfiguracionAporte
        fields = ['id', 'tipo', 'orden', 'cuenta']
