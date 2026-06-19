from rest_framework import serializers

from general.models import GenResolucion


class GenResolucionExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de resoluciones.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenResolucion
    nombre_archivo = 'resoluciones'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('prefijo', 'Prefijo'),
        ('numero', 'Número'),
        ('clave_tecnica', 'Clave técnica'),
        ('set_prueba', 'Set prueba'),
        ('consecutivo_desde', 'Consecutivo desde'),
        ('consecutivo_hasta', 'Consecutivo hasta'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('venta', 'Venta'),
        ('compra', 'Compra'),
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
