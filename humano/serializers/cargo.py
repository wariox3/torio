from rest_framework import serializers

from humano.models import HumCargo


class HumCargoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'codigo', 'nombre', 'estado_inactivo'}
    ordenamiento_default_lista = ('nombre',)

    class Meta:
        model = HumCargo
        fields = ['id', 'codigo', 'nombre', 'estado_inactivo']
        read_only_fields = ['id']
