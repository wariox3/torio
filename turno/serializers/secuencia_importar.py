from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from turno.models import TurSecuencia, TurTurno
from turno.serializers.secuencia import CAMPOS_DIAS, CAMPOS_SEMANA
from turno.serializers.secuencia_exportar import _ENCABEZADOS_SEMANA

# Ranuras que guardan código de turno -> etiqueta (posición) mostrada en errores.
_CAMPOS_RANURAS = (*CAMPOS_DIAS, *CAMPOS_SEMANA)
_ETIQUETAS_RANURA = {
    **{campo: f'Día {campo.split("_")[1]}' for campo in CAMPOS_DIAS},
    **{campo: _ENCABEZADOS_SEMANA[campo] for campo in CAMPOS_SEMANA},
}


class TurSecuenciaImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de secuencias y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = TurSecuencia
    nombre_archivo = 'secuencias'

    campos_excel = (
        ('nombre', 'Nombre'),
        *((campo, f'Día {campo.split("_")[1]}') for campo in CAMPOS_DIAS),
        *((campo, _ENCABEZADOS_SEMANA[campo]) for campo in CAMPOS_SEMANA),
        ('horas', 'Horas'),
        ('dias', 'Días'),
        ('homologar', 'Homologar'),
        ('estado_inactivo', 'Inactivo'),
    )
    campos_requeridos = {'nombre'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # Pre-cargar los códigos de turno existentes (una sola query para todo el lote).
        codigos_archivo = {
            codigo
            for _, datos in filas_validas
            for campo in _CAMPOS_RANURAS
            if (codigo := self._texto_o_none(datos.get(campo)))
        }
        codigos_existentes = set(
            TurTurno.objects.filter(codigo__in=codigos_archivo).values_list('codigo', flat=True)
        ) if codigos_archivo else set()

        errores = []
        nuevos = []
        nombres_vistos = set()

        for idx, datos in filas_validas:
            try:
                nombre = self._texto(datos.get('nombre'))
                if not nombre:
                    raise ValueError('El nombre es requerido')
                if nombre in nombres_vistos:
                    raise ValueError(f'Nombre duplicado en el archivo: "{nombre}"')
                nombres_vistos.add(nombre)

                campos = {
                    'nombre': nombre,
                    'horas': self._entero(datos.get('horas'), 'Horas'),
                    'dias': self._entero(datos.get('dias'), 'Días'),
                    'homologar': self._si_no(datos.get('homologar')),
                    'estado_inactivo': self._si_no(datos.get('estado_inactivo')),
                }
                faltantes = []
                for campo in _CAMPOS_RANURAS:
                    codigo = self._texto_o_none(datos.get(campo))
                    campos[campo] = codigo
                    if codigo and codigo not in codigos_existentes:
                        faltantes.append(f'{_ETIQUETAS_RANURA[campo]}: "{codigo}"')
                if faltantes:
                    raise ValueError('Turnos inexistentes -> ' + '; '.join(faltantes))

                nuevos.append(TurSecuencia(**campos))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            TurSecuencia.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
    def _entero(v, etiqueta, defecto=0):
        if v is None or str(v).strip() == '':
            return defecto
        try:
            return int(Decimal(str(v).strip()))
        except (InvalidOperation, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número entero, recibido: "{v}"')

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
