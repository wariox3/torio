from rest_framework import serializers

from contabilidad.models import ConMetodoDepreciacion


class ConMetodoDepreciacionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConMetodoDepreciacion
        fields = ['id', 'nombre']
