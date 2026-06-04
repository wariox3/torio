from rest_framework import serializers

from contabilidad.models import ConConciliacion


class ConConciliacionExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de conciliaciones.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = ConConciliacion
    nombre_archivo = 'conciliaciones'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('cuenta_banco.nombre', 'Cuenta banco'),
        ('cuenta_banco.numero_cuenta', 'Número cuenta'),
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
