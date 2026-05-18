from rest_framework import serializers

from general.models import GenDocumentoDetalle


class GenDocumentoDetalleSerializer(serializers.ModelSerializer):
    item_nombre = serializers.CharField(source='item.nombre', read_only=True)

    class Meta:
        model = GenDocumentoDetalle
        fields = [
            'id',
            'tipo_registro',
            'cantidad',
            'precio',
            'porcentaje_descuento',
            'detalle',
            'numero',
            'item',
            'item_nombre',
            'cuenta',
            'contacto',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
        ]
        read_only_fields = [
            'id',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
        ]
