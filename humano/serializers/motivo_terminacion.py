from rest_framework import serializers

from humano.models import HumMotivoTerminacion


class HumMotivoTerminacionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumMotivoTerminacion
        fields = ['id', 'nombre']
