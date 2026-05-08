from rest_framework import serializers

from contenedor.models import CtnIdentificacion


class CtnIdentificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnIdentificacion
        fields = ['id', 'nombre', 'orden', 'codigo', 'pais']


class CtnIdentificacionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnIdentificacion
        fields = ['id', 'nombre']
