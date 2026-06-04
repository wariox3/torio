from rest_framework import serializers

from humano.models import HumContrato


class HumContratoSeleccionarSerializer(serializers.ModelSerializer):
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = HumContrato
        fields = ['id', 'contacto', 'contacto_nombre', 'fecha_desde', 'fecha_hasta', 'estado_terminado']
