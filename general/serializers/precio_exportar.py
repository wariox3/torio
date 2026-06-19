from rest_framework import serializers

from general.models import GenPrecio


class GenPrecioExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de precios.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenPrecio
    nombre_archivo = 'precios'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('venta', 'Venta'),
        ('compra', 'Compra'),
        ('fecha_vence', 'Fecha vence'),
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
