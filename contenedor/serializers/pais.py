from rest_framework import serializers

from contenedor.models import CtnPais


class CtnPaisSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnPais
        fields = ['id', 'nombre', 'codigo']
