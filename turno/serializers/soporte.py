from rest_framework import serializers

from turno.models import TurSoporte


class TurSoporteSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha_desde', 'fecha_hasta', 'fecha_hasta_periodo', 'grupo',
    }
    select_related_lista = (
        'grupo',
    )
    ordenamiento_default_lista = ('fecha_desde', 'id')

    grupo_nombre = serializers.CharField(source='grupo.nombre', read_only=True, default=None)

    class Meta:
        model = TurSoporte
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'fecha_hasta_periodo',
            'grupo',
            'grupo_nombre',
        ]
        read_only_fields = ['id']
