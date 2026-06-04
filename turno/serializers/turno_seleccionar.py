from rest_framework import serializers

from turno.models import TurTurno


class TurTurnoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurTurno
        fields = ['id', 'nombre', 'codigo']
