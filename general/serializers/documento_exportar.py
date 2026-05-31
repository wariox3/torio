from rest_framework import serializers

from general.models import GenDocumento


class GenDocumentoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de documentos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenDocumento
    nombre_archivo = 'documentos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('fecha_contable', 'Fecha contable'),
        ('documento_tipo.nombre', 'Tipo documento'),
        ('contacto.nombre_corto', 'Contacto'),
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
