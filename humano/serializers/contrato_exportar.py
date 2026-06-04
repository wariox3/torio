from rest_framework import serializers

from humano.models import HumContrato


class HumContratoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de contratos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumContrato
    nombre_archivo = 'contratos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('contacto.numero_identificacion', 'Identificación'),
        ('contacto.nombre_corto', 'Empleado'),
        ('contrato_tipo.nombre', 'Tipo contrato'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('salario', 'Salario'),
        ('auxilio_transporte', 'Auxilio transporte'),
        ('salario_integral', 'Salario integral'),
        ('grupo.nombre', 'Grupo'),
        ('sucursal.nombre', 'Sucursal'),
        ('cargo.nombre', 'Cargo'),
        ('tipo_cotizante.nombre', 'Tipo cotizante'),
        ('subtipo_cotizante.nombre', 'Subtipo cotizante'),
        ('riesgo.nombre', 'Riesgo'),
        ('salud.nombre', 'Salud'),
        ('pension.nombre', 'Pensión'),
        ('entidad_salud.nombre', 'Entidad salud'),
        ('entidad_pension.nombre', 'Entidad pensión'),
        ('entidad_cesantias.nombre', 'Entidad cesantías'),
        ('entidad_caja.nombre', 'Entidad caja'),
        ('tiempo.nombre', 'Tiempo'),
        ('tipo_costo.nombre', 'Tipo costo'),
        ('grupo_contabilidad.nombre', 'Centro de costo'),
        ('estado_terminado', 'Terminado'),
        ('motivo_terminacion.nombre', 'Motivo terminación'),
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
