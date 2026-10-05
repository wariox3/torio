from rest_framework import serializers

from humano.models import HumAporteDetalle


class HumAporteDetalleExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de detalles del aporte: una
    fila por línea de la PILA.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumAporteDetalle
    nombre_archivo = 'aporte_detalles'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('aporte_contrato.aporte_id', 'Aporte'),
        ('aporte_contrato.id', 'Aporte contrato'),
        ('aporte_contrato.contrato.id', 'Contrato'),
        ('aporte_contrato.contrato.contacto.numero_identificacion', 'Identificación'),
        ('aporte_contrato.contrato.contacto.nombre_corto', 'Empleado'),
        ('horas', 'Horas'),
        ('dias_pension', 'Días pensión'),
        ('dias_salud', 'Días salud'),
        ('dias_riesgos', 'Días riesgos'),
        ('dias_caja', 'Días caja'),
        ('dias_incapacidad_laboral', 'Días incapacidad laboral'),
        ('base_cotizacion_pension', 'IBC pensión'),
        ('base_cotizacion_salud', 'IBC salud'),
        ('base_cotizacion_riesgos', 'IBC riesgos'),
        ('base_cotizacion_caja', 'IBC caja'),
        ('base_cotizacion_otros_parafiscales', 'IBC otros parafiscales'),
        ('tarifa_pension', 'Tarifa pensión'),
        ('tarifa_salud', 'Tarifa salud'),
        ('tarifa_riesgos', 'Tarifa riesgos'),
        ('tarifa_caja', 'Tarifa caja'),
        ('tarifa_sena', 'Tarifa SENA'),
        ('tarifa_icbf', 'Tarifa ICBF'),
        ('cotizacion_pension', 'Cotización pensión'),
        ('cotizacion_voluntario_pension_afiliado', 'Voluntario pensión afiliado'),
        ('cotizacion_voluntario_pension_aportante', 'Voluntario pensión aportante'),
        ('cotizacion_solidaridad_solidaridad', 'Fondo solidaridad'),
        ('cotizacion_solidaridad_subsistencia', 'Fondo subsistencia'),
        ('total_cotizacion_pension', 'Total cotización pensión'),
        ('cotizacion_salud', 'Cotización salud'),
        ('cotizacion_riesgos', 'Cotización riesgos'),
        ('cotizacion_caja', 'Cotización caja'),
        ('cotizacion_sena', 'Cotización SENA'),
        ('cotizacion_icbf', 'Cotización ICBF'),
        ('cotizacion_total', 'Cotización total'),
        ('upc_adicional', 'UPC adicional'),
        ('ingreso', 'ING'),
        ('retiro', 'RET'),
        ('variacion_permanente_salario', 'VSP'),
        ('variacion_transitoria_salario', 'VST'),
        ('suspension_temporal_contrato', 'SLN'),
        ('incapacidad_general', 'IGE'),
        ('licencia_maternidad', 'LMA'),
        ('vacaciones', 'VAC'),
        ('licencia_remunerada', 'Licencia remunerada'),
        ('aporte_voluntario_pension', 'AVP'),
        ('variacion_centro_trabajo', 'VCT'),
        ('salario_integral', 'Salario integral'),
        ('fecha_ingreso', 'Fecha ingreso'),
        ('fecha_retiro', 'Fecha retiro'),
        ('fecha_inicio_variacion_permanente_salario', 'Inicio VSP'),
        ('fecha_inicio_suspension_temporal_contrato', 'Inicio SLN'),
        ('fecha_fin_suspension_temporal_contrato', 'Fin SLN'),
        ('fecha_inicio_incapacidad_general', 'Inicio IGE'),
        ('fecha_fin_incapacidad_general', 'Fin IGE'),
        ('fecha_inicio_licencia_maternidad', 'Inicio LMA'),
        ('fecha_fin_licencia_maternidad', 'Fin LMA'),
        ('fecha_inicio_vacaciones', 'Inicio VAC'),
        ('fecha_fin_vacaciones', 'Fin VAC'),
        ('fecha_inicio_incapacidad_laboral', 'Inicio IRL'),
        ('fecha_fin_incapacidad_laboral', 'Fin IRL'),
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
