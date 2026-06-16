from rest_framework import serializers

from general.models import GenMetodoPago


class GenMetodoPagoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenMetodoPago
        fields = ['id', 'nombre', 'codigo']
