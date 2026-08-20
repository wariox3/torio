from rest_framework import serializers

from general.models import GenPrecioDetalle


class GenPrecioDetalleSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'precio_id', 'item_id', 'vr_precio', 'item__nombre', 'item__codigo'}
    select_related_lista = ('item',)
    ordenamiento_default_lista = ('-id',)

    item_nombre = serializers.CharField(source='item.nombre', read_only=True, default=None)
    item_codigo = serializers.CharField(source='item.codigo', read_only=True, default=None)
    item_referencia = serializers.CharField(source='item.referencia', read_only=True, default=None)

    class Meta:
        model = GenPrecioDetalle
        fields = [
            'id',
            'precio',
            'item',
            'item_nombre',
            'item_codigo',
            'item_referencia',
            'vr_precio',
        ]
        read_only_fields = ['id']
