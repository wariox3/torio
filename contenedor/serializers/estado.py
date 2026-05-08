from rest_framework import serializers

from contenedor.models import CtnEstado


class CtnEstadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnEstado
        fields = ['id', 'nombre', 'codigo', 'pais']


class CtnEstadoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnEstado
        fields = ['id', 'nombre']
