from rest_framework import serializers

from general.models import GenResolucion


class GenResolucionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'prefijo', 'numero',
        'consecutivo_desde', 'consecutivo_hasta',
        'fecha_desde', 'fecha_hasta', 'venta', 'compra', 'estado_validado', 'estado_inactivo',
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
            'estado_validado',
            'estado_inactivo',
        ]
        # `estado_validado` solo lo cambia `validar`: es un hecho comprobado
        # contra la DIAN, no algo que el cliente afirme.
        read_only_fields = ['id', 'estado_validado']


class GenResolucionSeleccionarSerializer(serializers.ModelSerializer):
    class Meta:
        model = GenResolucion
        fields = ['id', 'prefijo', 'numero']
