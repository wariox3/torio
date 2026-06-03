from rest_framework import serializers

from turno.models import TurPuesto


class TurPuestoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurPuesto
        fields = ['id', 'nombre']
