from rest_framework import serializers

from general.models import GenDocumento, GenDocumentoDetalle, GenDocumentoImpuesto, GenImpuesto


class GenDocumentoImpuestoSerializer(serializers.ModelSerializer):
    impuesto_nombre = serializers.CharField(source='impuesto.nombre', read_only=True, default=None)
    impuesto_operacion = serializers.IntegerField(source='impuesto.operacion', read_only=True, default=None)

    class Meta:
        model = GenDocumentoImpuesto
        fields = [
            'id',
            'impuesto',
            'impuesto_nombre',
            'impuesto_operacion',
            'base',
            'porcentaje',
            'porcentaje_base',
            'total',
        ]
        read_only_fields = ['id', 'base', 'porcentaje', 'porcentaje_base', 'total']


class GenDocumentoDetalleSerializer(serializers.ModelSerializer):
    campos_filtrables = {'id', 'documento_id', 'documento_detalle_afectado_id', 'item_id', 'tipo_registro', 'naturaleza', 'cuenta_id', 'centro_costo_id', 'contacto_id', 'contacto__nombre_corto', 'contacto__numero_identificacion', 'modalidad_id', 'almacen_id', 'afectado', 'pendiente'}
    select_related_lista = ('item', 'modalidad', 'cuenta', 'centro_costo', 'contacto', 'puesto', 'almacen')
    ordenamiento_default_lista = ('-id',)

    documento = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumento.objects.all(), required=False,
    )
    documento_detalle_afectado = serializers.PrimaryKeyRelatedField(
        queryset=GenDocumentoDetalle.objects.all(),
        required=False,
        allow_null=True,
    )
    item_nombre = serializers.CharField(source='item.nombre', read_only=True, default=None)
    modalidad_nombre = serializers.CharField(source='modalidad.nombre', read_only=True, default=None)
    modalidad_codigo = serializers.CharField(source='modalidad.codigo', read_only=True, default=None)
    puesto_nombre = serializers.CharField(source='puesto.nombre', read_only=True, default=None)
    centro_costo_nombre = serializers.CharField(source='centro_costo.nombre', read_only=True, default=None)
    centro_costo_codigo = serializers.CharField(source='centro_costo.codigo', read_only=True, default=None)
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, default=None)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, default=None)
    contacto_numero_identificacion = serializers.CharField(
        source='contacto.numero_identificacion', read_only=True, default=None,
    )
    contacto_nombre_corto = serializers.CharField(
        source='contacto.nombre_corto', read_only=True, default=None,
    )
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True, default=None)
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
    # Días/festivo: si no llegan en el create, se guardan en False.
    # En el PATCH (partial) los que no lleguen quedan sin cambios.
    lunes = serializers.BooleanField(required=False, default=False)
    martes = serializers.BooleanField(required=False, default=False)
    miercoles = serializers.BooleanField(required=False, default=False)
    jueves = serializers.BooleanField(required=False, default=False)
    viernes = serializers.BooleanField(required=False, default=False)
    sabado = serializers.BooleanField(required=False, default=False)
    domingo = serializers.BooleanField(required=False, default=False)
    festivo = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = GenDocumentoDetalle
        fields = [
            'id',
            'documento',
            'documento_detalle_afectado',
            'tipo_registro',
            # Lado del apunte contable (D/C). El valor va en `precio`; ver
            # `GenDocumentoDetalle.calcular`, que no deriva totales para estas líneas.
            'naturaleza',
            'cantidad',
            'precio',
            'precio_minimo',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
            'horas_programadas',
            'horas_diurnas_programadas',
            'horas_nocturnas_programadas',
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
            'cuenta_codigo',
            'cuenta_nombre',
            'centro_costo',
            'centro_costo_nombre',
            'centro_costo_codigo',
            'contacto',
            'contacto_numero_identificacion',
            'contacto_nombre_corto',
            'almacen',
            'almacen_nombre',
            'base',
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
            'generado',
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
