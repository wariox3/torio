from rest_framework import serializers

from turno.models import TurProgramador


class TurProgramadorImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de programadores y la
    lógica de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = TurProgramador
    nombre_archivo = 'programadores'

    campos_excel = (
        ('nombre', 'Nombre'),
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

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                nuevos.append(TurProgramador(
                    nombre=self._texto(datos.get('nombre')),
                    estado_inactivo=self._si_no(datos.get('estado_inactivo')),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            TurProgramador.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _texto(v):
        if v is None:
            return ''
        return str(v).strip()

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
