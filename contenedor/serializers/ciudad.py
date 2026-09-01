from rest_framework import serializers

from contenedor.models import CtnCiudad


class CtnCiudadSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnCiudad
        fields = ['id', 'nombre', 'latitud', 'longitud', 'codigo_postal', 'porcentaje_impuesto', 'estado']


class CtnCiudadSeleccionarSerializer(serializers.ModelSerializer):
    departamento_nombre = serializers.CharField(source='estado.nombre', read_only=True)

    class Meta:
        model = CtnCiudad
        fields = ['id', 'nombre', 'departamento_nombre']
