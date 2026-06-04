import datetime
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from turno.models import TurTurno


class TurTurnoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de turnos y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = TurTurno
    nombre_archivo = 'turnos'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('codigo', 'Código'),
        ('hora_inicio', 'Hora inicio'),
        ('hora_fin', 'Hora fin'),
        ('horas', 'Horas'),
        ('horas_diurnas', 'Horas diurnas'),
        ('horas_nocturnas', 'Horas nocturnas'),
        ('color', 'Color'),
        ('estado_inactivo', 'Inactivo'),
    )
    campos_requeridos = {'nombre', 'codigo', 'hora_inicio', 'hora_fin'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        errores = []
        nuevos = []
        codigos_vistos = set()

        for idx, datos in filas_validas:
            try:
                codigo = self._texto(datos.get('codigo'))
                if codigo in codigos_vistos:
                    raise ValueError(f'Código duplicado en el archivo: "{codigo}"')
                codigos_vistos.add(codigo)

                nuevos.append(TurTurno(
                    nombre=self._texto(datos.get('nombre')),
                    codigo=codigo,
                    hora_inicio=self._hora(datos.get('hora_inicio'), 'Hora inicio'),
                    hora_fin=self._hora(datos.get('hora_fin'), 'Hora fin'),
                    horas=self._decimal(datos.get('horas'), 'Horas'),
                    horas_diurnas=self._decimal(datos.get('horas_diurnas'), 'Horas diurnas'),
                    horas_nocturnas=self._decimal(datos.get('horas_nocturnas'), 'Horas nocturnas'),
                    color=self._texto_o_none(datos.get('color')),
                    estado_inactivo=self._si_no(datos.get('estado_inactivo')),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            TurTurno.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _texto(v):
        if v is None:
            return ''
        return str(v).strip()

    @staticmethod
    def _texto_o_none(v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()

    @staticmethod
    def _decimal(v, etiqueta, defecto=Decimal('0')):
        if v is None or str(v).strip() == '':
            return defecto
        try:
            return Decimal(str(v).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número, recibido: "{v}"')

    @staticmethod
    def _hora(v, etiqueta):
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es requerido')
        if isinstance(v, datetime.time):
            return v
        if isinstance(v, datetime.datetime):
            return v.time()
        texto = str(v).strip()
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.datetime.strptime(texto, fmt).time()
            except ValueError:
                continue
        raise ValueError(f'{etiqueta} debe ser una hora HH:MM, recibido: "{v}"')

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
