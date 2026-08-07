from rest_framework import serializers

from inventario.models import InvAlmacen


class InvAlmacenSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvAlmacen
        fields = ['id', 'nombre']
