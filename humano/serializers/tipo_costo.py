from rest_framework import serializers

from humano.models import HumTipoCosto


class HumTipoCostoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = HumTipoCosto
        fields = ['id', 'nombre']
