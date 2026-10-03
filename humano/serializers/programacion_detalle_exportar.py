from rest_framework import serializers

from humano.models import HumProgramacionDetalle


class HumProgramacionDetalleExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de detalles de programación.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumProgramacionDetalle
    nombre_archivo = 'programacion_detalles'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('programacion.id', 'Programación'),
        ('contrato.id', 'Contrato'),
        ('contrato.contacto.numero_identificacion', 'Identificación'),
        ('contrato.contacto.nombre_corto', 'Empleado'),
        ('fecha_desde', 'Desde'),
        ('fecha_hasta', 'Hasta'),
        ('dias', 'Días'),
        ('dias_transporte', 'Días transporte'),
        ('dias_novedad', 'Días novedad'),
        ('salario', 'Salario'),
        ('salario_promedio', 'Salario promedio'),
        ('base_prestacion', 'Base prestación'),
        ('diurna', 'Diurna'),
        ('nocturna', 'Nocturna'),
        ('festiva_diurna', 'Festiva diurna'),
        ('festiva_nocturna', 'Festiva nocturna'),
        ('extra_diurna', 'Extra diurna'),
        ('extra_nocturna', 'Extra nocturna'),
        ('extra_festiva_diurna', 'Extra festiva diurna'),
        ('extra_festiva_nocturna', 'Extra festiva nocturna'),
        ('recargo_nocturno', 'Recargo nocturno'),
        ('recargo_festivo_diurno', 'Recargo festivo diurno'),
        ('recargo_festivo_nocturno', 'Recargo festivo nocturno'),
        ('devengado', 'Devengado'),
        ('deduccion', 'Deducción'),
        ('total', 'Total'),
        ('ingreso', 'Ingreso'),
        ('retiro', 'Retiro'),
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
