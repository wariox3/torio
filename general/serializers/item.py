from django.db import transaction
from rest_framework import serializers

from general.models import GenImpuesto, GenItem, GenItemImpuesto


class GenItemImpuestoSerializer(serializers.ModelSerializer):
    impuesto_nombre = serializers.CharField(source='impuesto.nombre', read_only=True, default=None)
    impuesto_nombre_extendido = serializers.CharField(source='impuesto.nombre_extendido', read_only=True, default=None)
    impuesto_porcentaje = serializers.DecimalField(
        source='impuesto.porcentaje', max_digits=10, decimal_places=2, read_only=True, default=None,
    )
    impuesto_porcentaje_base = serializers.DecimalField(
        source='impuesto.porcentaje_base', max_digits=10, decimal_places=2, read_only=True, default=None,
    )
    impuesto_venta = serializers.BooleanField(source='impuesto.venta', read_only=True, default=None)
    impuesto_compra = serializers.BooleanField(source='impuesto.compra', read_only=True, default=None)
    impuesto_operacion = serializers.IntegerField(source='impuesto.operacion', read_only=True, default=None)
    impuesto_impuesto_tipo_id = serializers.IntegerField(source='impuesto.impuesto_tipo_id', read_only=True, default=None)

    class Meta:
        model = GenItemImpuesto
        fields = [
            'id',
            'impuesto',
            'impuesto_nombre',
            'impuesto_nombre_extendido',
            'impuesto_porcentaje',
            'impuesto_porcentaje_base',
            'impuesto_venta',
            'impuesto_compra',
            'impuesto_operacion',
            'impuesto_impuesto_tipo_id',
        ]
        read_only_fields = ['id']


class GenItemSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'nombre', 'codigo', 'referencia',
        'producto', 'servicio', 'inventario', 'favorito', 'venta', 'inactivo',
    }
    select_related_lista = (
        'cuenta_venta', 'cuenta_compra', 'cuenta_costo_venta', 'cuenta_inventario',
    )
    prefetch_related_lista = ('items_impuestos_item_rel__impuesto',)
    ordenamiento_default_lista = ('nombre',)

    cuenta_venta_nombre = serializers.CharField(source='cuenta_venta.nombre', read_only=True)
    cuenta_compra_nombre = serializers.CharField(source='cuenta_compra.nombre', read_only=True)
    cuenta_costo_venta_nombre = serializers.CharField(source='cuenta_costo_venta.nombre', read_only=True)
    cuenta_inventario_nombre = serializers.CharField(source='cuenta_inventario.nombre', read_only=True)
    impuestos = GenItemImpuestoSerializer(
        many=True,
        read_only=True,
        source='items_impuestos_item_rel',
    )
    impuestos_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        write_only=True,
        required=False,
        queryset=GenImpuesto.objects.all(),
    )

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
            'impuestos',
            'impuestos_ids',
        ]
        read_only_fields = ['id']

    @transaction.atomic
    def create(self, validated_data):
        impuestos = validated_data.pop('impuestos_ids', [])
        item = super().create(validated_data)
        self._sincronizar_impuestos(item, impuestos)
        return item

    @transaction.atomic
    def update(self, instance, validated_data):
        impuestos = validated_data.pop('impuestos_ids', None)
        item = super().update(instance, validated_data)
        if impuestos is not None:
            self._sincronizar_impuestos(item, impuestos, reemplazar=True)
        return item

    @staticmethod
    def _sincronizar_impuestos(item, impuestos, reemplazar=False):
        if reemplazar:
            item.items_impuestos_item_rel.all().delete()
        GenItemImpuesto.objects.bulk_create(
            [GenItemImpuesto(item=item, impuesto=impuesto) for impuesto in impuestos],
            ignore_conflicts=True,
        )
