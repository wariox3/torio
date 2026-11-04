from rest_framework import serializers

from venta.models import VenCaja


class VenCajaSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = VenCaja
        fields = ['id', 'nombre']
