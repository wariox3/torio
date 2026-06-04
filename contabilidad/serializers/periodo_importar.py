from rest_framework import serializers

from contabilidad.models import ConPeriodo


class ConPeriodoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de periodos y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = ConPeriodo
    nombre_archivo = 'periodos'

    campos_excel = (
        ('anio', 'Año'),
        ('mes', 'Mes'),
    )
    campos_requeridos = {'anio', 'mes'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                nuevos.append(ConPeriodo(
                    anio=self._entero(datos.get('anio'), 'Año'),
                    mes=self._entero(datos.get('mes'), 'Mes'),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            ConPeriodo.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _entero(v, etiqueta):
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es obligatorio')
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un entero, recibido: "{v}"')
