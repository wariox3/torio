from rest_framework import serializers

from humano.models import HumAporteEntidad


class HumAporteEntidadSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'aporte', 'entidad', 'tipo'}
    select_related_lista = ('aporte', 'entidad')
    ordenamiento_default_lista = ('-id',)

    entidad_nombre = serializers.CharField(source='entidad.nombre', read_only=True, default=None)

    class Meta:
        model = HumAporteEntidad
        fields = ['id', 'tipo', 'cotizacion', 'aporte', 'entidad', 'entidad_nombre']
        read_only_fields = ['id']
