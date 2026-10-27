from django.db import transaction
from django.db.models import F, Sum
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from general.models import (
    GenDocumento,
    GenDocumentoImpuesto,
    GenDocumentoTipo,
)
from general.models.documento import DOCUMENTO_TIPO_FACTURA_VENTA
from general.serializers.documento_detalle import GenDocumentoDetalleSerializer
from general.servicios import crear_detalle
from general.servicios.documento import (
    CONCEPTO_CORRECCION_OBLIGATORIO,
    DOCUMENTO_CLASE_DOCUMENTO_SOPORTE,
    DOCUMENTO_CLASE_NOTA_AJUSTE,
)


class GenDocumentoSerializer(serializers.ModelSerializer):
    campos_filtrables = {
        'id', 'numero', 'fecha', 'fecha_vence', 'documento_tipo_id', 'documento_tipo__nombre',
        'contacto_id', 'contrato_id', 'documento_referencia_id',
        'contacto__nombre_corto', 'contacto__numero_identificacion',
        'centro_costo_id', 'estado_aprobado', 'estado_anulado', 'estado_contabilizado',
        # Los pendientes por notificar son `estado_electronico=True` y
        # `estado_electronico_notificado=False`: sin el primero saldrían también las
        # que la DIAN todavía no ha validado, que no se pueden notificar.
        'estado_electronico', 'estado_electronico_enviado', 'estado_electronico_notificado',
        'estado_electronico_descartado', 'estado_electronico_error',
        'afectado', 'pendiente',
        # Banderas del tipo: permiten acotar por naturaleza del documento sin
        # tener que enumerar los ids de tipo que caen de cada lado.
        'documento_tipo__pagar', 'documento_tipo__cobrar',
        'documento_tipo__venta', 'documento_tipo__compra',
        'documento_tipo__contabilidad', 'documento_tipo__electronico',
        'documento_tipo__documento_clase_id',
        'documento_tipo__documento_clase__grupo',
        # Nóminas generadas por una programación: el renglón del empleado o la
        # programación completa.
        'programacion_detalle_id', 'programacion_detalle__programacion_id',
    }
    select_related_lista = ('documento_tipo', 'documento_tipo__cuenta_cobrar', 'documento_tipo__cuenta_pagar', 'contacto', 'contacto__precio', 'sector', 'sede', 'centro_costo', 'plazo_pago', 'metodo_pago', 'forma_pago', 'comprobante', 'cuenta_banco',
                             'almacen', 'asesor', 'resolucion', 'documento_concepto_correccion',
                             'documento_referencia')
    ordenamiento_default_lista = ('-fecha', '-numero')

    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    documento_tipo_operacion = serializers.IntegerField(source='documento_tipo.operacion', read_only=True)
    documento_tipo_cuenta_cobrar_id = serializers.IntegerField(source='documento_tipo.cuenta_cobrar_id', read_only=True, allow_null=True)
    documento_tipo_cuenta_cobrar_codigo = serializers.CharField(source='documento_tipo.cuenta_cobrar.codigo', read_only=True, allow_null=True)
    documento_tipo_cuenta_cobrar_nombre = serializers.CharField(source='documento_tipo.cuenta_cobrar.nombre', read_only=True, allow_null=True)
    documento_tipo_cuenta_pagar_id = serializers.IntegerField(source='documento_tipo.cuenta_pagar_id', read_only=True, allow_null=True)
    documento_tipo_cuenta_pagar_codigo = serializers.CharField(source='documento_tipo.cuenta_pagar.codigo', read_only=True, allow_null=True)
    documento_tipo_cuenta_pagar_nombre = serializers.CharField(source='documento_tipo.cuenta_pagar.nombre', read_only=True, allow_null=True)
    contacto_nombre_corto = serializers.CharField(source='contacto.nombre_corto', read_only=True, allow_null=True)
    contacto_numero_identificacion = serializers.CharField(source='contacto.numero_identificacion', read_only=True, allow_null=True)
    contacto_precio_id = serializers.IntegerField(source='contacto.precio_id', read_only=True, allow_null=True)
    contacto_precio_nombre = serializers.CharField(source='contacto.precio.nombre', read_only=True, allow_null=True)
    resolucion_numero = serializers.CharField(source='resolucion.numero', read_only=True, allow_null=True)
    resolucion_prefijo = serializers.CharField(source='resolucion.prefijo', read_only=True, allow_null=True)
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True, allow_null=True)
    plazo_pago_nombre = serializers.CharField(source='plazo_pago.nombre', read_only=True, allow_null=True)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True, allow_null=True)
    documento_referencia_numero = serializers.IntegerField(
        source='documento_referencia.numero', read_only=True, allow_null=True,
    )
    documento_concepto_correccion_nombre = serializers.CharField(
        source='documento_concepto_correccion.nombre', read_only=True, allow_null=True,
    )
    forma_pago_nombre = serializers.CharField(source='forma_pago.nombre', read_only=True, allow_null=True)
    asesor_nombre = serializers.CharField(source='asesor.nombre_corto', read_only=True, allow_null=True)
    cuenta_banco_nombre = serializers.CharField(
        source='cuenta_banco.nombre', read_only=True, allow_null=True,
    )
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True, allow_null=True)
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, allow_null=True)
    centro_costo_nombre = serializers.CharField(source='centro_costo.nombre', read_only=True, allow_null=True)
    centro_costo_codigo = serializers.CharField(source='centro_costo.codigo', read_only=True, allow_null=True)
    comprobante_nombre = serializers.CharField(source='comprobante.nombre', read_only=True, allow_null=True)
    comprobante_codigo = serializers.CharField(source='comprobante.codigo', read_only=True, allow_null=True)

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
            'resolucion_numero',
            'resolucion_prefijo',
            'plazo_pago',
            'plazo_pago_nombre',
            'metodo_pago',
            'metodo_pago_nombre',
            'documento_concepto_correccion',
            'documento_concepto_correccion_nombre',
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
            'documento_referencia_numero',
            'subtotal',
            'descuento',
            'total_bruto',
            'base_impuesto',
            'impuesto',
            'impuesto_retencion',
            'total',
            'debito',
            'credito',
            'cantidad_detalles',
            'afectado',
            'pago',
            'pendiente',
            'salario',
            # Nómina: IBC (`base_cotizacion`) e IBP (`base_prestacion`).
            'devengado',
            'deduccion',
            'base_cotizacion',
            'base_prestacion',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
            'horas_programadas',
            'horas_diurnas_programadas',
            'horas_nocturnas_programadas',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
            # Los escriben el webhook de rededoc y la notificación, nunca el front:
            # escribibles, una factura podría quedar como validada sin que la DIAN
            # la hubiera aceptado.
            'estado_electronico',
            'estado_electronico_enviado',
            'estado_electronico_notificado',
            'estado_electronico_descartado',
            'estado_electronico_error',
            # El CUFE (o CUDS) con que la DIAN validó el documento.
            'cue',
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
            # Los calcula `recalcular_totales` de las líneas de cuenta.
            'debito',
            'credito',
            # Lo cuenta `recalcular_totales`.
            'cantidad_detalles',
            # Saldo de cartera: lo fija `aprobar` y lo mueven las afectaciones y
            # los pagos. Escribible sería dejar que el cliente se invente el saldo.
            'afectado',
            'pendiente',
            # Suma de los `GenDocumentoPago` no anulados; solo lo escribe
            # `servicios.documento_pago`.
            'pago',
            # Totales de la nómina: los calcula la liquidación.
            'devengado',
            'deduccion',
            'base_cotizacion',
            'base_prestacion',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
            # Los escriben el webhook de rededoc y la notificación, nunca el front:
            # escribibles, una factura podría quedar como validada sin que la DIAN
            # la hubiera aceptado.
            'estado_electronico',
            'estado_electronico_enviado',
            'estado_electronico_notificado',
            'estado_electronico_descartado',
            'estado_electronico_error',
            'cue',
        ]

    def validate(self, datos):
        self._heredar_resolucion(datos)
        self._validar_concepto_correccion(datos)
        self._validar_referencia_nota_ajuste(datos)
        return self._seguir_fecha(datos)

    def _validar_concepto_correccion(self, datos):
        """
        El concepto de corrección tiene que ser de la clase del documento, y en
        la nota crédito y la nota de ajuste es obligatorio
        (`CONCEPTO_CORRECCION_OBLIGATORIO`).

        Cada clase de nota tiene su lista y los códigos se repiten entre ellas: el
        «2» de la nota crédito anula la factura y el de la nota débito son gastos
        por cobrar. Uno de otra clase le diría a la DIAN algo distinto de lo que
        se eligió.
        """
        if 'documento_concepto_correccion' in datos:
            concepto = datos['documento_concepto_correccion']
        else:
            concepto = getattr(self.instance, 'documento_concepto_correccion', None)
        tipo = datos.get('documento_tipo') or getattr(self.instance, 'documento_tipo', None)
        if concepto is None:
            # Sin él no se puede emitir.
            if tipo is not None and tipo.documento_clase_id in CONCEPTO_CORRECCION_OBLIGATORIO:
                raise serializers.ValidationError({
                    'documento_concepto_correccion':
                        CONCEPTO_CORRECCION_OBLIGATORIO[tipo.documento_clase_id],
                })
            return
        if tipo is None or concepto.documento_clase_id != tipo.documento_clase_id:
            raise serializers.ValidationError({
                'documento_concepto_correccion':
                    'El concepto de corrección no corresponde a este tipo de documento.',
            })

    def _validar_referencia_nota_ajuste(self, datos):
        """
        La nota de ajuste lleva siempre el documento soporte que ajusta.

        rededoc no tiene «nota de ajuste sin referencia» (las notas de venta sí),
        y una vez aprobada la referencia ya no se puede cambiar: sin esta regla
        la nota se aprobaría y nunca se podría emitir. Que ese documento soporte
        ya esté validado por la DIAN se revisa al emitir, porque puede llegar
        después de guardar la nota.
        """
        tipo = datos.get('documento_tipo') or getattr(self.instance, 'documento_tipo', None)
        if tipo is None or tipo.documento_clase_id != DOCUMENTO_CLASE_NOTA_AJUSTE:
            return
        if 'documento_referencia' in datos:
            referencia = datos['documento_referencia']
        else:
            referencia = getattr(self.instance, 'documento_referencia', None)
        if referencia is None:
            raise serializers.ValidationError({
                'documento_referencia': 'La nota de ajuste debe indicar el documento soporte que ajusta.',
            })
        if referencia.documento_tipo.documento_clase_id != DOCUMENTO_CLASE_DOCUMENTO_SOPORTE:
            raise serializers.ValidationError({
                'documento_referencia': 'La nota de ajuste solo puede ajustar un documento soporte.',
            })

    def _heredar_resolucion(self, datos):
        """
        La factura de venta toma siempre la resolución de su tipo.

        Es contra esa resolución que se valida el consecutivo al aprobar y la que
        viaja a rededoc al emitir: si la eligiera quien digita, una factura podría
        numerarse contra otra resolución que la configurada. La que mande el front
        se descarta. Solo corre al guardar por la API, y un documento aprobado ya
        no se edita, así que la factura conserva la resolución con la que se numeró
        aunque después cambie la del tipo.
        """
        tipo = datos.get('documento_tipo') or getattr(self.instance, 'documento_tipo', None)
        if tipo is not None and tipo.pk == DOCUMENTO_TIPO_FACTURA_VENTA:
            datos['resolucion'] = tipo.resolucion

    def _seguir_fecha(self, datos):
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


class GenDocumentoImpuestoResumenSerializer(serializers.Serializer):
    """Un renglón por impuesto del documento, con base y valores sumados."""

    impuesto_id = serializers.IntegerField()
    impuesto_nombre = serializers.CharField()
    impuesto_nombre_extendido = serializers.CharField()
    impuesto_operacion = serializers.IntegerField()
    base = serializers.DecimalField(max_digits=20, decimal_places=6)
    total = serializers.DecimalField(max_digits=20, decimal_places=6)
    total_operado = serializers.DecimalField(max_digits=20, decimal_places=6)


class GenDocumentoConImpuestosSerializer(GenDocumentoSerializer):
    """El documento de `GET /documento/{id}/` más sus impuestos agrupados."""

    documento_impuestos = serializers.SerializerMethodField()

    class Meta(GenDocumentoSerializer.Meta):
        fields = GenDocumentoSerializer.Meta.fields + ['documento_impuestos']

    @extend_schema_field(GenDocumentoImpuestoResumenSerializer(many=True))
    def get_documento_impuestos(self, documento):
        # Primero los que se cobran (IVA, ICA…) y después las retenciones, como en
        # la factura impresa.
        filas = (
            GenDocumentoImpuesto.objects
            .filter(documento_detalle__documento=documento)
            .values(
                'impuesto_id',
                impuesto_nombre=F('impuesto__nombre'),
                impuesto_nombre_extendido=F('impuesto__nombre_extendido'),
                impuesto_operacion=F('impuesto__operacion'),
            )
            .annotate(base=Sum('base'), total=Sum('total'), total_operado=Sum('total_operado'))
            .order_by('-impuesto_operacion', 'impuesto_id')
        )
        return GenDocumentoImpuestoResumenSerializer(filas, many=True).data


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

    Que falten los dos lo ataja el servicio (`generar_recurrente`) y no un
    `validate()`: desde acá DRF devolvería `detail` como lista y no como texto.
    """

    documento_tipo_origen = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(), required=False,
    )
    # `allow_empty` a propósito: mandar `documento_ids: []` junto con el tipo es la
    # forma natural de decir "sin ids". Que falten los dos lo ataja el servicio.
    documento_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, allow_empty=True,
    )
    documento_tipo_destino = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoTipo.objects.all(),
    )
    anio = serializers.IntegerField(min_value=1900, max_value=9999)
    mes = serializers.IntegerField(min_value=1, max_value=12)
    # Requerido a propósito: decide si se respeta la fecha de cada plantilla, y
    # un default escondería esa decisión.
    validar_fechas = serializers.BooleanField()
