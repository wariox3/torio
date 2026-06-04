from rest_framework import serializers

from humano.models import HumLiquidacion


class HumLiquidacionExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de liquidaciones.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumLiquidacion
    nombre_archivo = 'liquidaciones'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('contrato.contacto.nombre_corto', 'Empleado'),
        ('fecha', 'Fecha'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('dias', 'Días'),
        ('cesantia', 'Cesantía'),
        ('interes', 'Interés'),
        ('prima', 'Prima'),
        ('vacacion', 'Vacación'),
        ('deduccion', 'Deducción'),
        ('adicion', 'Adición'),
        ('total', 'Total'),
        ('salario', 'Salario'),
        ('estado_aprobado', 'Aprobado'),
        ('estado_generado', 'Generado'),
        ('comentario', 'Comentario'),
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
