from rest_framework import serializers

from general.models import GenContacto


class GenContactoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenContacto
        fields = ['id', 'nombre_corto', 'numero_identificacion']
