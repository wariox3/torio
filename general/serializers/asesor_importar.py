from rest_framework import serializers

from general.models import GenAsesor


class GenAsesorImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de asesores y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenAsesor
    nombre_archivo = 'asesores'

    campos_excel = (
        ('nombre_corto', 'Nombre corto'),
        ('celular', 'Celular'),
        ('correo', 'Correo'),
    )
    campos_requeridos = {'nombre_corto'}

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
                nuevos.append(GenAsesor(
                    nombre_corto=self._texto(datos.get('nombre_corto')),
                    celular=self._texto(datos.get('celular')),
                    correo=self._texto(datos.get('correo')),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            GenAsesor.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _texto(v):
        if v is None:
            return ''
        return str(v).strip()
