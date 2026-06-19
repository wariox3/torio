from rest_framework import serializers

from general.models import GenResolucion


class GenResolucionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'prefijo', 'numero',
        'consecutivo_desde', 'consecutivo_hasta',
        'fecha_desde', 'fecha_hasta', 'venta', 'compra',
    }
    ordenamiento_default_lista = ('numero',)

    class Meta:
        model = GenResolucion
        fields = [
            'id',
            'prefijo',
            'numero',
            'clave_tecnica',
            'set_prueba',
            'consecutivo_desde',
            'consecutivo_hasta',
            'fecha_desde',
            'fecha_hasta',
            'venta',
            'compra',
        ]
        read_only_fields = ['id']


class GenResolucionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenResolucion
        fields = ['id', 'prefijo', 'numero']
