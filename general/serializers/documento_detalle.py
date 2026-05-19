from rest_framework import serializers

from general.models import GenDocumentoDetalle


class GenDocumentoDetalleSerializer(serializers.ModelSerializer):
    item_nombre = serializers.CharField(source='item.nombre', read_only=True, default=None)
    modalidad_nombre = serializers.CharField(source='modalidad.nombre', read_only=True, default=None)

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
            'modalidad',
            'modalidad_nombre',
            'cuenta',
            'contacto',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'hora_desde',
            'hora_hasta',
            'lunes',
            'martes',
            'miercoles',
            'jueves',
            'viernes',
            'sabado',
            'domingo',
            'festivo',
            'programar',
            'cortesia',
            'compuesto',
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
