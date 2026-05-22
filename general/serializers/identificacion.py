from rest_framework import serializers

from general.models import GenIdentificacion


class GenIdentificacionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenIdentificacion
        fields = ['id', 'nombre', 'tipo_persona']
