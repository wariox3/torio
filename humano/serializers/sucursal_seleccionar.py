from rest_framework import serializers

from humano.models import HumSucursal


class HumSucursalSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumSucursal
        fields = ['id', 'nombre', 'codigo']
