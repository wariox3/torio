from rest_framework import serializers

from contenedor.models import CtnSuscripcionTipo


class CtnSuscripcionTipoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnSuscripcionTipo
        fields = ['id', 'nombre', 'precio', 'suscripcion_clase_id']
        read_only_fields = ['id']
