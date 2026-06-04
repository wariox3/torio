from rest_framework import serializers

from humano.models import HumProgramacion


class HumProgramacionExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de programaciones.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumProgramacion
    nombre_archivo = 'programaciones'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('fecha_hasta_periodo', 'Fecha hasta periodo'),
        ('grupo.nombre', 'Grupo'),
        ('pago_tipo.nombre', 'Tipo pago'),
        ('periodo.nombre', 'Periodo'),
        ('dias', 'Días'),
        ('dias_reales', 'Días reales'),
        ('contratos', 'Contratos'),
        ('devengado', 'Devengado'),
        ('deduccion', 'Deducción'),
        ('total', 'Total'),
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
