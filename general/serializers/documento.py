from django.db import transaction
from rest_framework import serializers

from general.models import GenDocumento, GenDocumentoDetalle
from general.serializers.documento_detalle import GenDocumentoDetalleSerializer


class GenDocumentoSerializer(serializers.ModelSerializer):
    campos_filtrables = {'id', 'numero', 'fecha', 'documento_tipo_id', 'contacto_id', 'estado_aprobado', 'estado_anulado', 'estado_contabilizado'}
    select_related_lista = ('documento_tipo', 'contacto', 'sector', 'modalidad')
    ordenamiento_default_lista = ('-fecha', '-numero')

    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    contacto_nombre = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True, default=None)
    modalidad_nombre = serializers.CharField(source='modalidad.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumento
        fields = [
            'id',
            'numero',
            'fecha',
            'fecha_contable',
            'fecha_vence',
            'fecha_desde',
            'fecha_hasta',
            'soporte',
            'orden_compra',
            'remision',
            'comentario',
            'documento_tipo',
            'documento_tipo_nombre',
            'contacto',
            'contacto_nombre',
            'resolucion',
            'plazo_pago',
            'asesor',
            'cuenta_banco',
            'comprobante',
            'cuenta',
            'sector',
            'sector_nombre',
            'modalidad',
            'modalidad_nombre',
            'estrato',
            'documento_referencia',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'salario',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
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
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
        ]


class GenDocumentoDetalleVistaSerializer(GenDocumentoSerializer):
    detalles = GenDocumentoDetalleSerializer(
        many=True,
        read_only=True,
        source='documentos_detalles_documento_rel',
    )

    class Meta(GenDocumentoSerializer.Meta):
        fields = GenDocumentoSerializer.Meta.fields + ['detalles']


class GenDocumentoCrearSerializer(GenDocumentoSerializer):
    detalles = GenDocumentoDetalleSerializer(
        many=True,
        required=False,
        source='documentos_detalles_documento_rel',
    )

    class Meta(GenDocumentoSerializer.Meta):
        fields = GenDocumentoSerializer.Meta.fields + ['detalles']

    @transaction.atomic
    def create(self, validated_data):
        detalles_data = validated_data.pop('documentos_detalles_documento_rel', [])
        documento = GenDocumento.objects.create(**validated_data)
        for detalle_data in detalles_data:
            detalle = GenDocumentoDetalle(documento=documento, **detalle_data)
            detalle.calcular()
            detalle.save()
        documento.recalcular_totales()
        documento.save()
        return documento
