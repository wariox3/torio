from rest_framework import serializers

from general.models import GenFormaPago


class GenFormaPagoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenFormaPago
        fields = ['id', 'nombre']
