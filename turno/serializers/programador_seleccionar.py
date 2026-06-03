from rest_framework import serializers

from turno.models import TurProgramador


class TurProgramadorSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurProgramador
        fields = ['id', 'nombre']
