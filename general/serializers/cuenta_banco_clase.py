from rest_framework import serializers

from general.models import GenCuentaBancoClase


class GenCuentaBancoClaseSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenCuentaBancoClase
        fields = ['id', 'nombre']
