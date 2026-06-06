from rest_framework import serializers

from general.models import GenDocumentoDetalle, GenDocumentoImpuesto, GenImpuesto


class GenDocumentoImpuestoSerializer(serializers.ModelSerializer):
    impuesto_nombre = serializers.CharField(source='impuesto.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumentoImpuesto
        fields = [
            'id',
            'impuesto',
            'impuesto_nombre',
            'base',
            'porcentaje',
            'porcentaje_base',
            'total',
        ]
        read_only_fields = ['id', 'base', 'porcentaje', 'porcentaje_base', 'total']


class GenDocumentoDetalleSerializer(serializers.ModelSerializer):
    campos_filtrables = {'id', 'documento_id', 'item_id', 'tipo_registro', 'cuenta_id', 'contacto_id', 'modalidad_id'}
    select_related_lista = ('item', 'modalidad', 'cuenta', 'contacto', 'puesto')
    ordenamiento_default_lista = ('-id',)

    item_nombre = serializers.CharField(source='item.nombre', read_only=True, default=None)
    modalidad_nombre = serializers.CharField(source='modalidad.nombre', read_only=True, default=None)
    modalidad_codigo = serializers.CharField(source='modalidad.codigo', read_only=True, default=None)
    puesto_nombre = serializers.CharField(source='puesto.nombre', read_only=True, default=None)
    impuestos = GenDocumentoImpuestoSerializer(
        many=True,
        read_only=True,
        source='documentos_impuestos_documento_detalle_rel',
    )
    impuestos_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        write_only=True,
        required=False,
        queryset=GenImpuesto.objects.all(),
    )

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
            'modalidad_codigo',
            'puesto',
            'puesto_nombre',
            'cuenta',
            'contacto',
            'impuestos',
            'impuestos_ids',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'hora_desde',
            'hora_hasta',
            'fecha_desde',
            'fecha_hasta',
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
