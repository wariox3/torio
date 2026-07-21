from rest_framework import serializers

from general.models import GenPlazoPago


class GenPlazoPagoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenPlazoPago
        fields = ['id', 'nombre', 'dias']
