from rest_framework import serializers

from general.models import GenFestivo


class GenFestivoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenFestivo
        fields = ['id', 'fecha', 'nombre']
