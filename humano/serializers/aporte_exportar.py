from rest_framework import serializers

from humano.models import HumAporte


class HumAporteExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de aportes.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumAporte
    nombre_archivo = 'aportes'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('anio', 'Año'),
        ('mes', 'Mes'),
        ('presentacion', 'Presentación'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('contratos', 'Contratos'),
        ('empleados', 'Empleados'),
        ('base_cotizacion', 'Base cotización'),
        ('cotizacion_pension_total', 'Cotización pensión'),
        ('cotizacion_salud', 'Cotización salud'),
        ('cotizacion_riesgos', 'Cotización riesgos'),
        ('cotizacion_caja', 'Cotización caja'),
        ('cotizacion_sena', 'Cotización SENA'),
        ('cotizacion_icbf', 'Cotización ICBF'),
        ('cotizacion_total', 'Cotización total'),
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
