from rest_framework import serializers

from general.models import GenBanco


class GenBancoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenBanco
        fields = ['id', 'nombre']
