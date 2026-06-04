from rest_framework import serializers

from humano.models import HumGrupo


class HumGrupoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'nombre', 'periodo'}
    select_related_lista = ('periodo',)
    ordenamiento_default_lista = ('nombre',)

    periodo_nombre = serializers.CharField(source='periodo.nombre', read_only=True, default=None)

    class Meta:
        model = HumGrupo
        fields = ['id', 'nombre', 'periodo', 'periodo_nombre']
        read_only_fields = ['id']
