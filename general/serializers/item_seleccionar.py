from rest_framework import serializers

from general.models import GenItem


class GenItemSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenItem
        fields = ['id', 'nombre', 'codigo', 'referencia', 'precio']
