from rest_framework import serializers

from humano.models import HumPagoTipo


class HumPagoTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumPagoTipo
        fields = ['id', 'nombre', 'aplica_programacion']
