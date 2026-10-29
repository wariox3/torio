from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from contabilidad.models import ConInconsistencia


class ConInconsistenciaExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de inconsistencias guardadas.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = ConInconsistencia
    nombre_archivo = 'inconsistencias'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('periodo_id', 'Periodo'),
        ('inconsistencia_tipo.nombre', 'Tipo de inconsistencia'),
        ('inconsistencia_tipo.resolver_automatico', 'Resolver automático'),
        ('comprobante.nombre', 'Comprobante'),
        ('numero', 'Número'),
        ('movimiento_id', 'Movimiento'),
        ('movimiento.cuenta.codigo', 'Cuenta'),
        ('documento_id', 'Documento'),
        ('documento.documento_tipo.nombre', 'Tipo de documento'),
        ('descripcion', 'Descripción'),
        ('fecha', 'Fecha análisis'),
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
        # Excel no admite zona horaria: la fecha va en hora local, sin tz.
        if isinstance(valor, datetime) and timezone.is_aware(valor):
            return timezone.localtime(valor).replace(tzinfo=None)
        return valor
