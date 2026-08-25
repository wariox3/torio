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
        # El unique_together lo reporta validate() con `detail`, no con non_field_errors.
        validators = []

    def validate(self, attrs):
        precio = attrs.get('precio', getattr(self.instance, 'precio', None))
        item = attrs.get('item', getattr(self.instance, 'item', None))

        qs = GenPrecioDetalle.objects.filter(precio=precio, item=item)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {'detail': 'Ya existe un detalle para ese precio e item.'}
            )

        return attrs
