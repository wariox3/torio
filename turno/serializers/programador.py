from rest_framework import serializers

from turno.models import TurProgramador


class TurProgramadorSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'nombre', 'estado_inactivo'}
    ordenamiento_default_lista = ('nombre',)

    class Meta:
        model = TurProgramador
        fields = ['id', 'nombre', 'estado_inactivo']
        read_only_fields = ['id']
