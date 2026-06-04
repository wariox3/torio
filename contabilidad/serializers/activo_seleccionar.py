from rest_framework import serializers

from contabilidad.models import ConActivo


class ConActivoSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConActivo
        fields = ['id', 'codigo', 'nombre']
