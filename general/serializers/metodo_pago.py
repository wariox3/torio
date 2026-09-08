from rest_framework import serializers

from general.models import GenMetodoPago


class GenMetodoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenMetodoPago
        fields = ['id', 'nombre', 'codigo']
