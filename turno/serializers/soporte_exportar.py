from rest_framework import serializers

from turno.models import TurSoporte


class TurSoporteExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de soportes.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = TurSoporte
    nombre_archivo = 'soportes'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('fecha_hasta_periodo', 'Fecha hasta periodo'),
        ('grupo.nombre', 'Grupo'),
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
