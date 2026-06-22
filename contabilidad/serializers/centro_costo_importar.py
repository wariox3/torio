from rest_framework import serializers

from contabilidad.models import ConCentroCosto


class ConCentroCostoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de centros de costo y la
    lógica de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = ConCentroCosto
    nombre_archivo = 'centros_costo'

    campos_excel = (
        ('codigo', 'Código'),
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

        # Pre-cargar códigos existentes en BD para detectar duplicados (codigo es unique)
        codigos = {
            self._texto_o_none(datos.get('codigo'))
            for _, datos in filas_validas
            if self._texto_o_none(datos.get('codigo'))
        }
        ya_existen = set(
            ConCentroCosto.objects
            .filter(codigo__in=codigos)
            .values_list('codigo', flat=True)
        ) if codigos else set()

        errores = []
        nuevos = []
        vistos = set()  # códigos duplicados intra-archivo

        for idx, datos in filas_validas:
            try:
                codigo = self._texto_o_none(datos.get('codigo'))

                if codigo is not None:
                    if codigo in vistos:
                        raise ValueError(f'El código {codigo} está duplicado dentro del archivo')
                    vistos.add(codigo)
                    if codigo in ya_existen:
                        raise ValueError(f'Ya existe un centro de costo con código {codigo}')

                nuevos.append(ConCentroCosto(
                    nombre=self._texto(datos.get('nombre')),
                    codigo=codigo,
                    estado_inactivo=self._si_no(datos.get('estado_inactivo')),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            ConCentroCosto.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
