from rest_framework import serializers

from turno.models import TurProgramacionSimulacion


class TurProgramacionSimulacionExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de programaciones simuladas.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = TurProgramacionSimulacion
    nombre_archivo = 'programaciones_simulacion'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('fecha', 'Fecha'),
        ('turno.nombre', 'Turno'),
        ('horas', 'Horas'),
        ('horas_diurnas', 'Horas diurnas'),
        ('horas_nocturnas', 'Horas nocturnas'),
        ('festivo', 'Festivo'),
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
