from rest_framework import serializers

from general.models import GenCuentaBancoTipo


class GenCuentaBancoTipoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenCuentaBancoTipo
        fields = ['id', 'nombre']
