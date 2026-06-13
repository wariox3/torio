from rest_framework import serializers

from turno.models import TurProgramacionSimulacion


class TurProgramacionSimulacionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha', 'turno', 'festivo',
    }
    select_related_lista = (
        'turno',
    )
    ordenamiento_default_lista = ('fecha', 'id')

    turno_nombre = serializers.CharField(source='turno.nombre', read_only=True, default=None)

    class Meta:
        model = TurProgramacionSimulacion
        fields = [
            'id',
            'fecha',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
            'festivo',
            'turno',
            'turno_nombre',
        ]
        read_only_fields = ['id']
