from rest_framework import serializers

from general.models import GenSede


class GenSedeSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {'id', 'nombre', 'codigo', 'centro_costo_id'}
    select_related_lista = ('centro_costo',)
    ordenamiento_default_lista = ('nombre',)

    centro_costo_nombre = serializers.CharField(source='centro_costo.nombre', read_only=True, default=None)
    centro_costo_codigo = serializers.CharField(source='centro_costo.codigo', read_only=True, default=None)

    class Meta:
        model = GenSede
        fields = [
            'id',
            'nombre',
            'codigo',
            'centro_costo',
            'centro_costo_nombre',
            'centro_costo_codigo',
        ]
        read_only_fields = ['id']
