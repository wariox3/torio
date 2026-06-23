from rest_framework import serializers

from turno.models import TurTurno


class TurTurnoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'nombre', 'codigo', 'estado_inactivo'}
    ordenamiento_default_lista = ('nombre',)

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
            'estado_inactivo',
        ]
        read_only_fields = ['id']
