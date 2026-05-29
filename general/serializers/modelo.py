from rest_framework import serializers

from general.models import GenModelo


class GenModeloSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model = GenModelo
        fields = ['id', 'app', 'clase', 'nombre', 'tabla', 'tipo', 'tipo_nombre']
        read_only_fields = ['id']
