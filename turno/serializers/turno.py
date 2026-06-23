from rest_framework import serializers

from turno.models import TurTurno


class TurTurnoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'nombre', 'codigo', 'estado_inactivo'}
    ordenamiento_default_lista = ('nombre',)

    novedad_tipo_nombre = serializers.CharField(source='novedad_tipo.nombre', read_only=True, default=None)

    class Meta:
        model = TurTurno
        fields = [
            'id',
            'nombre',
            'codigo',
            'hora_inicio',
            'hora_fin',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
            'color',
            'novedad_tipo',
            'novedad_tipo_nombre',
            'estado_inactivo',
        ]
        read_only_fields = ['id']
