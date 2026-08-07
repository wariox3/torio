from rest_framework import serializers

from inventario.models import InvAlmacen


class InvAlmacenImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de almacenes y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = InvAlmacen
    nombre_archivo = 'almacenes'

    campos_excel = (
        ('nombre', 'Nombre'),
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

        # El modelo no tiene código: el nombre es la única forma de identificar el
        # almacén, así que se usa como clave natural para rechazar repetidos
        # (el import solo crea, no actualiza).
        nombres = {
            self._texto_o_none(datos.get('nombre'))
            for _, datos in filas_validas
            if self._texto_o_none(datos.get('nombre'))
        }
        ya_existen = set(
            InvAlmacen.objects
            .filter(nombre__in=nombres)
            .values_list('nombre', flat=True)
        ) if nombres else set()

        errores = []
        nuevos = []
        vistos = set()  # nombres duplicados intra-archivo

        for idx, datos in filas_validas:
            try:
                nombre = self._texto(datos.get('nombre'))

                if nombre in vistos:
                    raise ValueError(f'El nombre {nombre} está duplicado dentro del archivo')
                vistos.add(nombre)
                if nombre in ya_existen:
                    raise ValueError(f'Ya existe un almacén con nombre {nombre}')

                nuevos.append(InvAlmacen(nombre=nombre))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            InvAlmacen.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
