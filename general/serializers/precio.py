from rest_framework import serializers

from general.models import GenPrecio


class GenPrecioSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {'id', 'nombre', 'venta', 'compra', 'fecha_vence'}
    ordenamiento_default_lista = ('-id',)

    class Meta:
        model = GenPrecio
        fields = ['id', 'nombre', 'venta', 'compra', 'fecha_vence']
        read_only_fields = ['id']


class GenPrecioSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenPrecio
        fields = ['id', 'nombre']
