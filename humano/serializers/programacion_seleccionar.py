from rest_framework import serializers

from humano.models import HumProgramacion


class HumProgramacionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumProgramacion
        fields = ['id', 'nombre', 'fecha_desde', 'fecha_hasta']
