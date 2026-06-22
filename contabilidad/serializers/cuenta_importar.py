from rest_framework import serializers

from contabilidad.models import ConCuenta


class ConCuentaImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de cuentas y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = ConCuenta
    nombre_archivo = 'cuentas'

    campos_excel = (
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('exige_base', 'Exige base'),
        ('exige_contacto', 'Exige contacto'),
        ('exige_grupo', 'Exige grupo'),
        ('permite_movimiento', 'Permite movimiento'),
    )
    campos_requeridos = {'nombre'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        Procesa todas las filas válidas en bulk:
          1. Valida cada fila en memoria (sin BD).
          2. `bulk_create` al final si no hay errores.

        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                nuevos.append(ConCuenta(
                    codigo=self._texto(datos.get('codigo')) or '0',
                    nombre=self._texto(datos.get('nombre')),
                    exige_base=self._si_no(datos.get('exige_base')),
                    exige_contacto=self._si_no(datos.get('exige_contacto')),
                    exige_grupo=self._si_no(datos.get('exige_grupo')),
                    permite_movimiento=self._si_no(datos.get('permite_movimiento')),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            ConCuenta.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
