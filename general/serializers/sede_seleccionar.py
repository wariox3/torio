from rest_framework import serializers

from general.models import GenSede


class GenSedeSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenSede
        fields = ['id', 'nombre', 'codigo']
