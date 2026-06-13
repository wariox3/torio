from rest_framework import serializers

from turno.models import TurPrototipo


class TurPrototipoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha', 'fecha_inicio', 'documento_detalle', 'secuencia',
    }
    select_related_lista = (
        'documento_detalle',
        'documento_detalle__puesto',
        'secuencia',
    )
    ordenamiento_default_lista = ('fecha', 'id')

    puesto_nombre = serializers.CharField(
        source='documento_detalle.puesto.nombre', read_only=True, default=None,
    )
    secuencia_nombre = serializers.CharField(
        source='secuencia.nombre', read_only=True, default=None,
    )

    class Meta:
        model = TurPrototipo
        fields = [
            'id',
            'fecha',
            'fecha_inicio',
            'documento_detalle',
            'puesto_nombre',
            'secuencia',
            'secuencia_nombre',
        ]
        read_only_fields = ['id']
