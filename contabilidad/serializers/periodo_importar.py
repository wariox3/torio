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
                anio = self._entero(datos.get('anio'), 'Año', 2000, 2100)
                mes = self._entero(datos.get('mes'), 'Mes', 1, 13)
                # El id se asigna explícito porque `bulk_create` no pasa por `save()`.
                nuevos.append(ConPeriodo(
                    id=ConPeriodo.calcular_id(anio, mes),
                    anio=anio,
                    mes=mes,
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
    def _entero(v, etiqueta, minimo, maximo):
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es obligatorio')
        try:
            valor = int(float(str(v).strip()))
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un entero, recibido: "{v}"')
        # El rango no es cosmético: el id del periodo es anio*100+mes, así que un
        # mes fuera de 1–13 codificaría el id de otro año.
        if not minimo <= valor <= maximo:
            raise ValueError(f'{etiqueta} debe estar entre {minimo} y {maximo}, recibido: "{v}"')
        return valor
