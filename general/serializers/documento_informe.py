from rest_framework import serializers

from general.models import GenDocumento


class GenDocumentoInformeSerializer(serializers.ModelSerializer):
    """
    Serializer estándar (plano, solo lectura) para los informes sobre GenDocumento.
    La invariante de cada informe la garantiza el ViewSet en `get_queryset`; aquí se
    define el contrato común de columnas y la whitelist de filtros/orden que consume
    `FiltrosDinamicosMixin`.
    """

    campos_filtrables = {
        'id',
        'numero',
        'fecha',
        'fecha_vence',
        'documento_tipo_id',
        'contacto_id',
        'contacto__nombre_corto',
        'contacto__numero_identificacion',
        'sector_id',
        'sede_id',
        'estado_aprobado',
        'estado_anulado',
        'estado_contabilizado',
    }
    select_related_lista = (
        'documento_tipo',
        'contacto',
        'sector',
        'sede',
        'plazo_pago',
        'metodo_pago',
        'forma_pago',
    )
    ordenamiento_default_lista = ('-fecha', '-numero')

    documento_tipo_nombre = serializers.CharField(source='documento_tipo.nombre', read_only=True)
    contacto_nombre_corto = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    contacto_numero_identificacion = serializers.CharField(
        source='contacto.numero_identificacion', read_only=True, default=None,
    )
    sector_nombre = serializers.CharField(source='sector.nombre', read_only=True, default=None)
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, default=None)
    plazo_pago_nombre = serializers.CharField(source='plazo_pago.nombre', read_only=True, default=None)
    metodo_pago_nombre = serializers.CharField(source='metodo_pago.nombre', read_only=True, default=None)
    forma_pago_nombre = serializers.CharField(source='forma_pago.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumento
        fields = [
            'id',
            'numero',
            'fecha',
            'fecha_vence',
            'documento_tipo_id',
            'documento_tipo_nombre',
            'contacto_id',
            'contacto_nombre_corto',
            'contacto_numero_identificacion',
            'sector_id',
            'sector_nombre',
            'sede_id',
            'sede_nombre',
            'plazo_pago_id',
            'plazo_pago_nombre',
            'metodo_pago_id',
            'metodo_pago_nombre',
            'forma_pago_id',
            'forma_pago_nombre',
            'subtotal',
            'descuento',
            'impuesto',
            'total',
            'afectado',
            'pendiente',
            'estado_aprobado',
            'estado_anulado',
            'estado_contabilizado',
        ]


class GenDocumentoInformeExportarSerializer(serializers.Serializer):
    """Estructura estándar del Excel de los informes (usada por ExportarExcelMixin)."""

    model = GenDocumento
    nombre_archivo = 'informe_documento'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('fecha_vence', 'Fecha vence'),
        ('documento_tipo.nombre', 'Tipo documento'),
        ('contacto.nombre_corto', 'Contacto'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('sector.nombre', 'Sector'),
        ('sede.nombre', 'Sede'),
        ('plazo_pago.nombre', 'Plazo de pago'),
        ('metodo_pago.nombre', 'Método de pago'),
        ('forma_pago.nombre', 'Forma de pago'),
        ('subtotal', 'Subtotal'),
        ('descuento', 'Descuento'),
        ('impuesto', 'Impuesto'),
        ('total', 'Total'),
        ('afectado', 'Afectado'),
        ('pendiente', 'Pendiente'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_contabilizado', 'Contabilizado'),
    )

    @staticmethod
    def valor_excel(obj, campo):
        valor = obj
        for parte in campo.split('.'):
            if valor is None:
                return None
            valor = getattr(valor, parte, None)
        if isinstance(valor, bool):
            return 'Sí' if valor else 'No'
        return valor


class GenDocumentoNominaInformeSerializer(serializers.ModelSerializer):
    """
    Columnas del informe `nomina`: un renglón por documento de nómina con el
    empleado, su cuenta, el grupo del contrato y los totales. La invariante (solo
    documentos de clase Nómina) la garantiza el ViewSet.
    """

    campos_filtrables = {
        'id',
        'numero',
        'fecha',
        'fecha_hasta',
        'contacto_id',
        'contacto__nombre_corto',
        'contacto__numero_identificacion',
        'contrato_id',
        'contrato__grupo_id',
        'programacion_detalle__programacion_id',
        'estado_aprobado',
        'estado_anulado',
        'estado_contabilizado',
        'estado_electronico',
    }
    select_related_lista = ('contacto', 'contacto__banco', 'contrato', 'contrato__grupo')
    ordenamiento_default_lista = ('-fecha', '-numero')

    contacto_numero_identificacion = serializers.CharField(
        source='contacto.numero_identificacion', read_only=True, default=None,
    )
    contacto_nombre_corto = serializers.CharField(source='contacto.nombre_corto', read_only=True, default=None)
    contacto_numero_cuenta = serializers.CharField(source='contacto.numero_cuenta', read_only=True, default=None)
    contacto_banco_nombre = serializers.CharField(source='contacto.banco.nombre', read_only=True, default=None)
    contrato_grupo_nombre = serializers.CharField(source='contrato.grupo.nombre', read_only=True, default=None)

    class Meta:
        model = GenDocumento
        fields = [
            'id',
            'numero',
            'fecha',
            'fecha_hasta',
            'contacto_id',
            'contacto_numero_identificacion',
            'contacto_nombre_corto',
            'contacto_numero_cuenta',
            'contacto_banco_nombre',
            'contrato_id',
            'contrato_grupo_nombre',
            'dias',
            'salario',
            'devengado',
            'deduccion',
            'total',
            'base_cotizacion',
            'base_prestacion',
            'estado_aprobado',
            'estado_anulado',
            'estado_electronico',
            'estado_contabilizado',
            'cue',
        ]


class GenDocumentoNominaInformeExportarSerializer(serializers.Serializer):
    """Estructura del Excel del informe `nomina` (usada por ExportarExcelMixin)."""

    model = GenDocumento
    nombre_archivo = 'nominas'
    hoja = 'Informe'

    campos_excel = (
        ('id', 'ID'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('fecha_hasta', 'Fecha hasta'),
        ('contacto_id', 'Contacto'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Empleado'),
        ('contacto.numero_cuenta', 'Cuenta'),
        ('contacto.banco.nombre', 'Banco'),
        ('contrato_id', 'Contrato'),
        ('contrato.grupo.nombre', 'Grupo'),
        ('dias', 'Días'),
        ('salario', 'Salario'),
        ('devengado', 'Devengado'),
        ('deduccion', 'Deducción'),
        ('total', 'Total'),
        ('base_cotizacion', 'Base cotización'),
        ('base_prestacion', 'Base prestación'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_electronico', 'Electrónico'),
        ('estado_contabilizado', 'Contabilizado'),
        ('cue', 'CUE'),
    )

    @staticmethod
    def valor_excel(obj, campo):
        valor = obj
        for parte in campo.split('.'):
            if valor is None:
                return None
            valor = getattr(valor, parte, None)
        if isinstance(valor, bool):
            return 'Sí' if valor else 'No'
        return valor
