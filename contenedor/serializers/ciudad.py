from rest_framework import serializers

from contenedor.models import CtnCiudad


class CtnCiudadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnCiudad
        fields = ['id', 'nombre', 'latitud', 'longitud', 'codigo_postal', 'porcentaje_impuesto', 'estado']


class CtnCiudadListaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnCiudad
        fields = ['id', 'nombre']
