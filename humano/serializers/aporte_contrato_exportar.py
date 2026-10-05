from rest_framework import serializers

from humano.models import HumAporteContrato


class HumAporteContratoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de contratos del aporte.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumAporteContrato
    nombre_archivo = 'aporte_contratos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('aporte.id', 'Aporte'),
        ('contrato.id', 'Contrato'),
        ('contrato.contacto.numero_identificacion', 'Identificación'),
        ('contrato.contacto.nombre_corto', 'Empleado'),
        ('fecha_desde', 'Desde'),
        ('fecha_hasta', 'Hasta'),
        ('dias', 'Días'),
        ('salario', 'Salario'),
        ('base_cotizacion', 'Base cotización'),
        ('cotizacion_pension', 'Cotización pensión'),
        ('cotizacion_pension_total', 'Cotización pensión total'),
        ('cotizacion_pension_empresa', 'Cotización pensión empresa'),
        ('cotizacion_pension_empleado', 'Cotización pensión empleado'),
        ('cotizacion_voluntario_pension_afiliado', 'Voluntario pensión afiliado'),
        ('cotizacion_voluntario_pension_aportante', 'Voluntario pensión aportante'),
        ('cotizacion_solidaridad_solidaridad', 'Fondo solidaridad'),
        ('cotizacion_solidaridad_subsistencia', 'Fondo subsistencia'),
        ('cotizacion_salud', 'Cotización salud'),
        ('cotizacion_salud_empresa', 'Cotización salud empresa'),
        ('cotizacion_salud_empleado', 'Cotización salud empleado'),
        ('cotizacion_riesgos', 'Cotización riesgos'),
        ('cotizacion_caja', 'Cotización caja'),
        ('cotizacion_sena', 'Cotización SENA'),
        ('cotizacion_icbf', 'Cotización ICBF'),
        ('cotizacion_total', 'Cotización total'),
        ('ingreso', 'Ingreso'),
        ('retiro', 'Retiro'),
        ('error_terminacion', 'Error terminación'),
        ('ciudad_labora.nombre', 'Ciudad labora'),
        ('entidad_salud.nombre', 'Entidad salud'),
        ('entidad_pension.nombre', 'Entidad pensión'),
        ('entidad_caja.nombre', 'Entidad caja'),
        ('entidad_riesgo.nombre', 'Entidad riesgos'),
        ('entidad_sena.nombre', 'Entidad SENA'),
        ('entidad_icbf.nombre', 'Entidad ICBF'),
        ('riesgo.nombre', 'Riesgo'),
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
