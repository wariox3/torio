from rest_framework import serializers

from humano.models import HumSucursal


class HumSucursalSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'codigo', 'nombre'}
    ordenamiento_default_lista = ('nombre',)

    class Meta:
        model = HumSucursal
        fields = ['id', 'nombre', 'codigo']
        read_only_fields = ['id']
