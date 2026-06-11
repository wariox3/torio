from rest_framework import serializers

from turno.models import TurSecuencia


class TurSecuenciaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurSecuencia
        fields = ['id', 'nombre', 'codigo']
