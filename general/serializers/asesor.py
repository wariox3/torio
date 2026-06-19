from rest_framework import serializers

from general.models import GenAsesor


class GenAsesorSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {'id', 'nombre_corto', 'celular', 'correo'}
    ordenamiento_default_lista = ('nombre_corto',)

    class Meta:
        model = GenAsesor
        fields = ['id', 'nombre_corto', 'celular', 'correo']
        read_only_fields = ['id']


class GenAsesorSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenAsesor
        fields = ['id', 'nombre_corto']
