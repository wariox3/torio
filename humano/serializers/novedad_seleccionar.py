from rest_framework import serializers

from humano.models import HumNovedad


class HumNovedadSeleccionarSerializer(serializers.ModelSerializer):
    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)
    novedad_tipo_nombre = serializers.CharField(source='novedad_tipo.nombre', read_only=True, default=None)

    class Meta:
        model = HumNovedad
        fields = ['id', 'contrato', 'contrato_nombre', 'novedad_tipo', 'novedad_tipo_nombre', 'fecha_desde', 'fecha_hasta']
