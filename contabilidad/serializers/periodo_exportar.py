from rest_framework import serializers

from contabilidad.models import ConPeriodo


class ConPeriodoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de periodos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = ConPeriodo
    nombre_archivo = 'periodos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('anio', 'Año'),
        ('mes', 'Mes'),
        ('estado_bloqueado', 'Bloqueado'),
        ('estado_cerrado', 'Cerrado'),
        ('estado_inconsistencia', 'Inconsistencia'),
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
