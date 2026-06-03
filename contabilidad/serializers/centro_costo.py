from rest_framework import serializers

from contabilidad.models import ConCentroCosto


class ConCentroCostoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'codigo', 'nombre'}
    ordenamiento_default_lista = ('codigo',)

    class Meta:
        model = ConCentroCosto
        fields = ['id', 'nombre', 'codigo']
        read_only_fields = ['id']
