from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from general.models import GenItem, GenPrecio, GenPrecioDetalle


class GenPrecioDetalleImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de detalles de precio y la
    lógica de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenPrecioDetalle
    nombre_archivo = 'precios_detalles'

    campos_excel = (
        ('precio.id', 'Precio'),
        ('item.id', 'Item'),
        ('vr_precio', 'Valor precio'),
    )
    campos_requeridos = {'precio.id', 'item.id', 'vr_precio'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        Procesa todas las filas válidas en bulk:
          1. Pre-carga FKs en una query por modelo.
          2. Pre-carga los pares (precio, item) ya usados en BD en una query.
          3. Valida cada fila contra mapas en memoria (sin BD).
          4. `bulk_create` al final si no hay errores.

        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs en mapas {id: instancia}
        ids_precio = self._ids_int(filas_validas, 'precio.id')
        ids_item = self._ids_int(filas_validas, 'item.id')

        mapa_precio = {o.id: o for o in GenPrecio.objects.filter(id__in=ids_precio)}
        mapa_item = {o.id: o for o in GenItem.objects.filter(id__in=ids_item)}

        # 2) Pares (precio, item) ya usados: en la BD y en el propio archivo.
        existentes = set(
            GenPrecioDetalle.objects
            .filter(precio_id__in=mapa_precio, item_id__in=mapa_item)
            .values_list('precio_id', 'item_id')
        )

        # 3) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                precio_id = int(datos['precio.id'])
                precio = mapa_precio.get(precio_id)
                if precio is None:
                    raise ValueError(f'Precio con id={precio_id} no existe')

                item = self._fk_obligatorio(datos.get('item.id'), mapa_item, 'Item')

                par = (precio.id, item.id)
                if par in existentes:
                    raise ValueError('Ya existe un detalle para ese precio e item')
                existentes.add(par)

                nuevos.append(GenPrecioDetalle(
                    precio=precio,
                    item=item,
                    vr_precio=self._decimal(datos.get('vr_precio'), 'Valor precio'),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        # 4) Bulk create (solo si no hubo errores)
        if errores:
            return 0, errores

        if nuevos:
            GenPrecioDetalle.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _ids_int(filas_validas, campo):
        """Extrae el conjunto de ids enteros para `campo` (ignora vacíos e inválidos)."""
        ids = set()
        for _, datos in filas_validas:
            valor = datos.get(campo)
            if valor in (None, ''):
                continue
            try:
                ids.add(int(valor))
            except (TypeError, ValueError):
                pass  # tipos inválidos ya fueron filtrados en la fase 1
        return ids

    @staticmethod
    def _fk_opcional(valor, mapa, etiqueta):
        if valor in (None, ''):
            return None
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número (PK), recibido: "{valor}"')
        obj = mapa.get(pk)
        if obj is None:
            raise ValueError(f'{etiqueta} con id={pk} no existe')
        return obj

    def _fk_obligatorio(self, valor, mapa, etiqueta):
        obj = self._fk_opcional(valor, mapa, etiqueta)
        if obj is None:
            raise ValueError(f'{etiqueta} es obligatorio')
        return obj

    @staticmethod
    def _decimal(v, etiqueta):
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es obligatorio')
        try:
            return Decimal(str(v).strip())
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número decimal (recibido: "{v}")')
