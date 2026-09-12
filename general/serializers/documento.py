from django.db import transaction
from rest_framework import serializers

from general.models import (
    GenDocumento,
    GenDocumentoTipo,
)
from general.serializers.documento_detalle import GenDocumentoDetalleSerializer
from general.servicios import crear_detalle


class GenDocumentoSerializer(serializers.ModelSerializer):
    campos_filtrables = {
        'id', 'numero', 'fecha', 'fecha_vence', 'documento_tipo_id', 'contacto_id',
        'contacto__nombre_corto', 'contacto__numero_identificacion',
        'centro_costo_id', 'estado_aprobado', 'estado_anulado', 'estado_contabilizado',
        'afectado', 'pendiente',
        # Banderas del tipo: permiten acotar por naturaleza del documento sin
        # tener que enumerar los ids de tipo que caen de cada lado.
        'documento_tipo__pagar', 'documento_tipo__cobrar',
        'documento_tipo__venta', 'documento_tipo__compra',
    }
    select_related_lista = ('documento_tipo', 'documento_tipo__cuenta_cobrar', 'documento_tipo__cuenta_pagar', 'contacto', 'contacto__precio', 'sector', 'sede', 'centro_costo', 'plazo_pago', 'metodo_pago', 'forma_pago', 'comprobante', 'cuenta_banco',
                             'almacen', 'asesor')
    ordenamiento_default_lista = ('-fecha', '-numero')

    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    documento_tipo_operacion = serializers.IntegerField(source='documento_tipo.operacion', read_only=True)
    documento_tipo_cuenta_cobrar_id = serializers.IntegerField(source='documento_tipo.cuenta_cobrar_id', read_only=True, default=None)
    documento_tipo_cuenta_cobrar_codigo = serializers.CharField(source='documento_tipo.cuenta_cobrar.codigo', read_only=True, default=None)
    documento_tipo_cuenta_cobrar_nombre = serializers.CharField(source='documento_tipo.cuenta_cobrar.nombre', read_only=True, default=None)
    documento_tipo_cuenta_pagar_id = serializers.IntegerField(source='documento_tipo.cuenta_pagar_id', read_only=True, default=None)
    documento_tipo_cuenta_pagar_codigo = serializers.CharField(source='documento_tipo.cuenta_pagar.codigo', read_only=True, default=None)
    documento_tipo_cuenta_pagar_nombre = serializers.CharField(source='documento_tipo.cuenta_pagar.nombre', read_only=True, default=None)
    contacto_nombre_corto = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    contacto_numero_identificacion = serializers.CharField(source='contacto.numero_identificacion', read_only=True, default=None)
    contacto_precio_id = serializers.IntegerField(source='contacto.precio_id', read_only=True, default=None)
    contacto_precio_nombre = serializers.CharField(source='contacto.precio.nombre', read_only=True, default=None)
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True, default=None)
    plazo_pago_nombre = serializers.CharField(source='plazo_pago.nombre', read_only=True, default=None)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True, default=None)
    forma_pago_nombre = serializers.CharField(source='forma_pago.nombre', read_only=True, default=None)
    asesor_nombre = serializers.CharField(source='asesor.nombre_corto', read_only=True, default=None)
    cuenta_banco_nombre = serializers.CharField(
        source='cuenta_banco.nombre', read_only=True, default=None,
    )
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True, default=None)
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, default=None)
    centro_costo_nombre = serializers.CharField(source='centro_costo.nombre', read_only=True, default=None)
    centro_costo_codigo = serializers.CharField(source='centro_costo.codigo', read_only=True, default=None)
    comprobante_nombre = serializers.CharField(source='comprobante.nombre', read_only=True, default=None)
    comprobante_codigo = serializers.CharField(source='comprobante.codigo', read_only=True, default=None)

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
            'documento_tipo_operacion',
            'documento_tipo_cuenta_cobrar_id',
            'documento_tipo_cuenta_cobrar_codigo',
            'documento_tipo_cuenta_cobrar_nombre',
            'documento_tipo_cuenta_pagar_id',
            'documento_tipo_cuenta_pagar_codigo',
            'documento_tipo_cuenta_pagar_nombre',
            'contacto',
            'contacto_nombre_corto',
            'contacto_numero_identificacion',
            'contacto_precio_id',
            'contacto_precio_nombre',
            'resolucion',
            'plazo_pago',
            'plazo_pago_nombre',
            'metodo_pago',
            'metodo_pago_nombre',
            'forma_pago',
            'forma_pago_nombre',
            'asesor',
            'asesor_nombre',
            'cuenta_banco',
            'cuenta_banco_nombre',
            'comprobante',
            'comprobante_codigo',
            'comprobante_nombre',
            'cuenta',
            'centro_costo',
            'centro_costo_nombre',
            'centro_costo_codigo',
            'sector',
            'sector_nombre',
            'sede',
            'sede_nombre',
            'almacen',
            'almacen_nombre',
            'estrato',
            'documento_referencia',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'afectado',
            'pendiente',
            'salario',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
            'horas_programadas',
            'horas_diurnas_programadas',
            'horas_nocturnas_programadas',
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
            # Saldo de cartera: lo fija `aprobar` y lo mueven las afectaciones y
            # los pagos. Escribible sería dejar que el cliente se invente el saldo.
            'afectado',
            'pendiente',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
        ]

    def validate(self, datos):
        """
        Mantiene `fecha_contable` a la par de `fecha` mientras nadie las separe.

        De `fecha_contable` sale el periodo al contabilizar. El sistema anterior
        la pisaba con `fecha` en cada guardado, lo que dejaba el campo inservible
        para nómina y aportes, que la usan justamente para apuntar a otro
        periodo. Acá sigue a `fecha` mientras vengan iguales —así al mover la
        fecha de un asiento se mueve también su periodo—, y apenas alguien la
        fija distinta se respeta y deja de seguirla.
        """
        if datos.get('fecha_contable'):
            return datos

        fecha = datos.get('fecha') or getattr(self.instance, 'fecha', None)
        if fecha is None:
            return datos

        anterior = getattr(self.instance, 'fecha_contable', None)
        if anterior and anterior != getattr(self.instance, 'fecha', None):
            # Ya venía separada a propósito: no se toca.
            return datos

        datos['fecha_contable'] = fecha
        return datos


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
            crear_detalle(documento, detalle_data)
        documento.recalcular_totales()
        documento.save()
        return documento


class GenDocumentoGenerarSerializer(serializers.Serializer):
    documento_tipo_id = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(),
    )
    documento_tipo_id_destino = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(),
    )
    documento_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True,
    )
    anio = serializers.IntegerField(min_value=1900, max_value=9999)
    mes = serializers.IntegerField(min_value=1, max_value=12)


class GenDocumentoGenerarRecurrenteSerializer(serializers.Serializer):
    """
    Las plantillas se eligen por tipo, por ids, o por los dos. Con
    `documento_tipo_origen` se toman todas las de ese tipo y los ids dejan de ser
    necesarios; mandando los dos, los ids acotan la selección del tipo.
    """

    documento_tipo_origen = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(), required=False,
    )
    # `allow_empty` a propósito: mandar `documento_ids: []` junto con el tipo es la
    # forma natural de decir "sin ids". Que falten los dos lo ataja `validate`.
    documento_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_empty=True,
    )
    documento_tipo_destino = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(),
    )
    anio = serializers.IntegerField(min_value=1900, max_value=9999)
    mes = serializers.IntegerField(min_value=1, max_value=12)

    def validate(self, datos):
        if not datos.get('documento_tipo_origen') and not datos.get('documento_ids'):
            raise serializers.ValidationError(
                'Debe enviar documento_tipo_origen o documento_ids.'
            )
        return datos
