from rest_framework import serializers

from humano.models import HumCredito


class HumCreditoExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de créditos.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = HumCredito
    nombre_archivo = 'creditos'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('contrato.contacto.nombre_corto', 'Empleado'),
        ('concepto.nombre', 'Concepto'),
        ('fecha_inicio', 'Fecha inicio'),
        ('total', 'Total'),
        ('cuota', 'Cuota'),
        ('abono', 'Abono'),
        ('saldo', 'Saldo'),
        ('cantidad_cuotas', 'Cantidad cuotas'),
        ('cuota_actual', 'Cuota actual'),
        ('validar_cuotas', 'Validar cuotas'),
        ('aplica_prima', 'Aplica prima'),
        ('aplica_cesantia', 'Aplica cesantía'),
        ('inactivo', 'Inactivo'),
        ('pagado', 'Pagado'),
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
