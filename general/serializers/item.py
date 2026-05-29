from rest_framework import serializers

from general.models import GenItem


class GenItemSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'nombre', 'codigo', 'referencia',
        'producto', 'servicio', 'inventario', 'favorito', 'venta', 'inactivo',
    }
    select_related_lista = (
        'cuenta_venta', 'cuenta_compra', 'cuenta_costo_venta', 'cuenta_inventario',
    )
    ordenamiento_default_lista = ('nombre',)

    cuenta_venta_nombre = serializers.CharField(source='cuenta_venta.nombre', read_only=True)
    cuenta_compra_nombre = serializers.CharField(source='cuenta_compra.nombre', read_only=True)
    cuenta_costo_venta_nombre = serializers.CharField(source='cuenta_costo_venta.nombre', read_only=True)
    cuenta_inventario_nombre = serializers.CharField(source='cuenta_inventario.nombre', read_only=True)

    class Meta:
        model = GenItem
        fields = [
            'id',
            'nombre',
            'codigo',
            'referencia',
            'costo_promedio',
            'costo_total',
            'costo',
            'precio',
            'producto',
            'servicio',
            'inventario',
            'negativo',
            'favorito',
            'venta',
            'inactivo',
            'existencia',
            'remision',
            'disponible',
            'imagen',
            'cuenta_venta',
            'cuenta_venta_nombre',
            'cuenta_compra',
            'cuenta_compra_nombre',
            'cuenta_costo_venta',
            'cuenta_costo_venta_nombre',
            'cuenta_inventario',
            'cuenta_inventario_nombre',
        ]
        read_only_fields = ['id']
