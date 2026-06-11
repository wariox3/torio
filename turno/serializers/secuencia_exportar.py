from rest_framework import serializers

from turno.models import TurSecuencia
from turno.serializers.secuencia import CAMPOS_DIAS, CAMPOS_SEMANA

_ENCABEZADOS_SEMANA = {
    'lunes': 'Lunes',
    'martes': 'Martes',
    'miercoles': 'Miércoles',
    'jueves': 'Jueves',
    'viernes': 'Viernes',
    'sabado': 'Sábado',
    'domingo': 'Domingo',
    'festivo': 'Festivo',
    'domingo_festivo': 'Domingo festivo',
}


class TurSecuenciaExportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de exportación de secuencias.

    Es consumido por `ExportarExcelMixin` a través del atributo
    `serializer_class_exportar` del ViewSet.
    """

    model = TurSecuencia
    nombre_archivo = 'secuencias'
    hoja = 'Datos'

    campos_excel = (
        ('id', 'ID'),
        ('nombre', 'Nombre'),
        ('codigo', 'Código'),
        *((campo, f'Día {campo.split("_")[1]}') for campo in CAMPOS_DIAS),
        *((campo, _ENCABEZADOS_SEMANA[campo]) for campo in CAMPOS_SEMANA),
        ('horas', 'Horas'),
        ('dias', 'Días'),
        ('homologar', 'Homologar'),
        ('estado_inactivo', 'Inactivo'),
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
