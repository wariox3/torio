from rest_framework import serializers

from general.models import GenDocumento


class GenDocumentoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de documentos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet. Es el Excel estándar: el que sale
    cuando el front no manda `documento_clase_id` o la clase no tiene perfil
    propio en `EXPORTAR_POR_CLASE`.

    `titulo` pone encima de la tabla el bloque de `ExportarExcelMixin`
    (título, empresa y fecha de generación); cada perfil trae el suyo. Este Excel
    no es plantilla del importar, que tiene sus propias columnas, así que la
    tabla puede arrancar debajo del bloque.

    `select_related_excel` son los FK que recorre `campos_excel`; el ViewSet los
    agrega al queryset para no hacer una consulta por fila.
    """

    model = GenDocumento
    nombre_archivo = 'documentos'
    titulo = 'Documentos'
    hoja = 'Datos'

    select_related_excel = ('documento_tipo', 'contacto', 'centro_costo', 'forma_pago')

    campos_excel = (
        ('id', 'ID'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('fecha_contable', 'Fecha contable'),
        ('documento_tipo.nombre', 'Tipo documento'),
        ('contacto.nombre_corto', 'Contacto'),
        ('centro_costo.codigo', 'Centro de costo'),
        ('centro_costo.nombre', 'Centro de costo nombre'),
        ('forma_pago.nombre', 'Forma pago'),
        ('soporte', 'Soporte'),
        ('orden_compra', 'Orden compra'),
        ('remision', 'Remisión'),
        ('comentario', 'Comentario'),
        ('subtotal', 'Subtotal'),
        ('descuento', 'Descuento'),
        ('total_bruto', 'Total bruto'),
        ('base_impuesto', 'Base impuesto'),
        ('impuesto', 'Impuesto'),
        ('impuesto_retencion', 'Retención'),
        ('total', 'Total'),
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


# ---------------------------------------------------- perfiles por clase ----
# Cada perfil cambia solo las columnas (y los FK que necesita). Las filas las
# siguen decidiendo los `filtros` del request.

_ENCABEZADO = (
    ('id', 'ID'),
    ('numero', 'Número'),
    ('fecha', 'Fecha'),
    ('documento_tipo.nombre', 'Tipo documento'),
)


class GenDocumentoVentaExportarSerializer(GenDocumentoExportarSerializer):
    nombre_archivo = 'documentos_venta'
    titulo = 'Documentos de venta'
    select_related_excel = ('documento_tipo', 'contacto', 'plazo_pago', 'metodo_pago', 'asesor', 'sede')

    campos_excel = _ENCABEZADO + (
        ('fecha_vence', 'Fecha vence'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Contacto'),
        ('plazo_pago.nombre', 'Plazo pago'),
        ('metodo_pago.nombre', 'Método pago'),
        ('asesor.nombre_corto', 'Asesor'),
        ('sede.nombre', 'Sede'),
        ('orden_compra', 'Orden compra'),
        ('remision', 'Remisión'),
        ('subtotal', 'Subtotal'),
        ('descuento', 'Descuento'),
        ('total_bruto', 'Total bruto'),
        ('base_impuesto', 'Base impuesto'),
        ('impuesto', 'Impuesto'),
        ('impuesto_retencion', 'Retención'),
        ('total', 'Total'),
        ('pendiente', 'Pendiente'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_electronico', 'Electrónico'),
        ('estado_contabilizado', 'Contabilizado'),
    )


class GenDocumentoCompraExportarSerializer(GenDocumentoExportarSerializer):
    nombre_archivo = 'documentos_compra'
    titulo = 'Documentos de compra'
    select_related_excel = ('documento_tipo', 'contacto', 'plazo_pago', 'forma_pago', 'sede')

    campos_excel = _ENCABEZADO + (
        ('fecha_vence', 'Fecha vence'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Contacto'),
        ('soporte', 'Soporte'),
        ('plazo_pago.nombre', 'Plazo pago'),
        ('forma_pago.nombre', 'Forma pago'),
        ('sede.nombre', 'Sede'),
        ('orden_compra', 'Orden compra'),
        ('remision', 'Remisión'),
        ('comentario', 'Comentario'),
        ('subtotal', 'Subtotal'),
        ('descuento', 'Descuento'),
        ('total_bruto', 'Total bruto'),
        ('base_impuesto', 'Base impuesto'),
        ('impuesto', 'Impuesto'),
        ('impuesto_retencion', 'Retención'),
        ('total', 'Total'),
        ('pendiente', 'Pendiente'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_electronico', 'Electrónico'),
        ('estado_contabilizado', 'Contabilizado'),
    )


class GenDocumentoPagoExportarSerializer(GenDocumentoExportarSerializer):
    """Pago (200) y egreso (400)."""

    nombre_archivo = 'documentos_pago'
    titulo = 'Pagos y egresos'
    select_related_excel = ('documento_tipo', 'contacto', 'cuenta_banco')

    campos_excel = _ENCABEZADO + (
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Contacto'),
        ('cuenta_banco.nombre', 'Cuenta banco'),
        ('comentario', 'Comentario'),
        ('total', 'Total'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_contabilizado', 'Contabilizado'),
    )


class GenDocumentoSaldoInicialExportarSerializer(GenDocumentoExportarSerializer):
    """Saldo inicial CXC (201) y CXP (401)."""

    nombre_archivo = 'documentos_saldo_inicial'
    titulo = 'Saldos iniciales'
    select_related_excel = ('documento_tipo', 'contacto')

    campos_excel = _ENCABEZADO + (
        ('fecha_vence', 'Fecha vence'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Contacto'),
        ('total', 'Total'),
        ('pendiente', 'Pendiente'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
    )


class GenDocumentoInventarioExportarSerializer(GenDocumentoExportarSerializer):
    """Entrada (500), salida (501) y traslado (502)."""

    nombre_archivo = 'documentos_inventario'
    titulo = 'Documentos de inventario'
    select_related_excel = ('documento_tipo', 'contacto', 'almacen')

    campos_excel = _ENCABEZADO + (
        ('contacto.nombre_corto', 'Contacto'),
        ('almacen.nombre', 'Almacén'),
        ('comentario', 'Comentario'),
        ('subtotal', 'Subtotal'),
        ('total', 'Total'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_contabilizado', 'Contabilizado'),
    )


class GenDocumentoContableExportarSerializer(GenDocumentoExportarSerializer):
    """Asiento (601), depreciación (602) y cierre (603)."""

    nombre_archivo = 'documentos_contables'
    titulo = 'Documentos contables'
    select_related_excel = ('documento_tipo', 'comprobante', 'contacto', 'centro_costo')

    campos_excel = _ENCABEZADO + (
        ('fecha_contable', 'Fecha contable'),
        ('comprobante.nombre', 'Comprobante'),
        ('contacto.nombre_corto', 'Contacto'),
        ('centro_costo.codigo', 'Centro de costo'),
        ('comentario', 'Comentario'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_contabilizado', 'Contabilizado'),
    )


class GenDocumentoNominaExportarSerializer(GenDocumentoExportarSerializer):
    """Nómina (701)."""

    nombre_archivo = 'documentos_nomina'
    titulo = 'Nóminas'
    select_related_excel = ('documento_tipo', 'contacto')

    campos_excel = _ENCABEZADO + (
        ('fecha_hasta', 'Fecha hasta'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Empleado'),
        ('contrato_id', 'Contrato'),
        ('dias', 'Días'),
        ('salario', 'Salario'),
        ('devengado', 'Devengado'),
        ('deduccion', 'Deducción'),
        ('total', 'Total'),
        ('base_cotizacion', 'Base cotización'),
        ('base_prestacion', 'Base prestación'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_anulado', 'Anulado'),
        ('estado_contabilizado', 'Contabilizado'),
    )


class GenDocumentoNominaElectronicaExportarSerializer(GenDocumentoExportarSerializer):
    """Nómina electrónica (702)."""

    nombre_archivo = 'documentos_nomina_electronica'
    titulo = 'Nóminas electrónicas'
    select_related_excel = ('documento_tipo', 'contacto')

    campos_excel = _ENCABEZADO + (
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Empleado'),
        ('devengado', 'Devengado'),
        ('deduccion', 'Deducción'),
        ('total', 'Total'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_electronico', 'Electrónico'),
        ('cue', 'CUE'),
    )


# Clase de documento → perfil. Una clase que no esté acá exporta el estándar.
EXPORTAR_POR_CLASE = {
    **{clase: GenDocumentoVentaExportarSerializer for clase in range(100, 111)},
    200: GenDocumentoPagoExportarSerializer,
    400: GenDocumentoPagoExportarSerializer,
    201: GenDocumentoSaldoInicialExportarSerializer,
    401: GenDocumentoSaldoInicialExportarSerializer,
    **{clase: GenDocumentoCompraExportarSerializer for clase in range(300, 306)},
    **{clase: GenDocumentoInventarioExportarSerializer for clase in (500, 501, 502)},
    **{clase: GenDocumentoContableExportarSerializer for clase in (601, 602, 603)},
    701: GenDocumentoNominaExportarSerializer,
    702: GenDocumentoNominaElectronicaExportarSerializer,
}
