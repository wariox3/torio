from rest_framework import serializers

from general.models import GenFormaPago


class GenFormaPagoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de formas de pago.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = GenFormaPago
    nombre_archivo = 'formas_pago'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('cuenta.nombre', 'Cuenta'),
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
