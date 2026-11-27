from rest_framework import serializers

from contabilidad.models import ConConciliacionDetalle


class ConConciliacionDetalleExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de los detalles (movimientos de libros) de una conciliación.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet. Respeta los mismos filtros de `lista`,
    así que filtrando por `conciliacion_id` y `estado_conciliado` sale lo que
    quedó sin cruzar.
    """

    model = ConConciliacionDetalle
    nombre_archivo = 'conciliaciones_detalles'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('fecha', 'Fecha'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('detalle', 'Detalle'),
        ('estado_conciliado', 'Conciliado'),
        ('cuenta.codigo', 'Cuenta código'),
        ('cuenta.nombre', 'Cuenta nombre'),
        ('contacto.numero_identificacion', 'Contacto identificación'),
        ('contacto.nombre_corto', 'Contacto nombre'),
        ('documento.documento_tipo.nombre', 'Documento tipo'),
        ('documento.numero', 'Documento número'),
        ('movimiento_id', 'Movimiento'),
    )

    @staticmethod
    def valor_excel(obj, campo):
        """Devuelve el valor a escribir en la celda para `obj` y `campo`."""
        valor = obj
        for parte in campo.split('.'):
            if valor is None:
                return None
            valor = getattr(valor, parte, None)
        if isinstance(valor, bool):
            return 'Sí' if valor else 'No'
        return valor
