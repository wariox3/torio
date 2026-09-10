from rest_framework import serializers

from contabilidad.models import ConCuenta
from general.models import GenImpuesto, GenItem, GenItemImpuesto


class GenItemImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de items y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenItem
    nombre_archivo = 'items'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('codigo', 'Código'),
        ('referencia', 'Referencia'),
        ('costo', 'Costo'),
        ('precio', 'Precio'),
        ('producto', 'Producto'),
        ('servicio', 'Servicio'),
        ('inventario', 'Inventario'),
        ('negativo', 'Negativo'),
        ('favorito', 'Favorito'),
        ('venta', 'Venta'),
        ('inactivo', 'Inactivo'),
        ('cuenta_venta.id', 'Cuenta venta'),
        ('cuenta_compra.id', 'Cuenta compra'),
        ('cuenta_costo_venta.id', 'Cuenta costo venta'),
        ('cuenta_inventario.id', 'Cuenta inventario'),
        ('impuestos', 'Impuestos'),
    )
    campos_requeridos = {'nombre'}

    # `impuestos` no es un campo del modelo sino una lista de ids, así que el
    # valor derivado de la plantilla saldría como «ejemplo 1» y no orientaría a
    # nadie. La segunda fila va vacía a propósito: la columna es opcional.
    valores_ejemplo = {'impuestos': ('1,3', '')}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        Procesa todas las filas válidas en bulk:
          1. Pre-carga FKs en una query por modelo.
          2. Pre-carga duplicados en BD en una query.
          3. Valida cada fila contra mapas en memoria (sin BD).
          4. `bulk_create` al final si no hay errores.

        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs (todas apuntan a ConCuenta) en un mapa {id: instancia}
        ids_cuenta = (
            self._ids_int(filas_validas, 'cuenta_venta.id')
            | self._ids_int(filas_validas, 'cuenta_compra.id')
            | self._ids_int(filas_validas, 'cuenta_costo_venta.id')
            | self._ids_int(filas_validas, 'cuenta_inventario.id')
        )
        mapa_cuenta = {o.id: o for o in ConCuenta.objects.filter(id__in=ids_cuenta)}

        ids_impuesto = set()
        for _, datos in filas_validas:
            ids_impuesto |= set(self._ids_lista(datos.get('impuestos')))
        impuestos_existentes = set(
            GenImpuesto.objects.filter(id__in=ids_impuesto).values_list('id', flat=True)
        )

        # 2) Pre-cargar códigos existentes en BD para detectar duplicados
        codigos = {
            self._texto(datos.get('codigo'))
            for _, datos in filas_validas
            if self._texto(datos.get('codigo'))
        }
        ya_existen = set(
            GenItem.objects
            .filter(codigo__in=codigos)
            .values_list('codigo', flat=True)
        ) if codigos else set()

        # 3) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []
        # Los impuestos de cada item, en el mismo orden que `nuevos`: la relación
        # necesita el id del item, que no existe hasta después del bulk_create.
        impuestos_por_item = []
        vistos = set()  # códigos duplicados intra-archivo

        for idx, datos in filas_validas:
            try:
                cuenta_venta = self._fk_opcional(datos.get('cuenta_venta.id'), mapa_cuenta, 'Cuenta venta')
                cuenta_compra = self._fk_opcional(datos.get('cuenta_compra.id'), mapa_cuenta, 'Cuenta compra')
                cuenta_costo_venta = self._fk_opcional(
                    datos.get('cuenta_costo_venta.id'), mapa_cuenta, 'Cuenta costo venta',
                )
                cuenta_inventario = self._fk_opcional(
                    datos.get('cuenta_inventario.id'), mapa_cuenta, 'Cuenta inventario',
                )

                impuestos = self._impuestos(datos.get('impuestos'), impuestos_existentes)

                codigo = self._texto_o_none(datos.get('codigo'))

                if codigo is not None:
                    if codigo in vistos:
                        raise ValueError(f'El código {codigo} está duplicado dentro del archivo')
                    vistos.add(codigo)
                    if codigo in ya_existen:
                        raise ValueError(f'Ya existe un item con código {codigo}')

                impuestos_por_item.append(impuestos)
                nuevos.append(GenItem(
                    nombre=self._texto(datos.get('nombre')),
                    codigo=codigo,
                    referencia=self._texto_o_none(datos.get('referencia')),
                    costo=self._decimal(datos.get('costo')),
                    precio=self._decimal(datos.get('precio')),
                    producto=self._si_no(datos.get('producto')),
                    servicio=self._si_no(datos.get('servicio')),
                    inventario=self._si_no(datos.get('inventario')),
                    negativo=self._si_no(datos.get('negativo')),
                    favorito=self._si_no(datos.get('favorito')),
                    venta=self._si_no(datos.get('venta'), defecto=True),
                    inactivo=self._si_no(datos.get('inactivo')),
                    cuenta_venta=cuenta_venta,
                    cuenta_compra=cuenta_compra,
                    cuenta_costo_venta=cuenta_costo_venta,
                    cuenta_inventario=cuenta_inventario,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        # 4) Bulk create (solo si no hubo errores)
        if errores:
            return 0, errores

        if nuevos:
            GenItem.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
            self._crear_impuestos(nuevos, impuestos_por_item)
        return len(nuevos), []

    def _crear_impuestos(self, items, impuestos_por_item):
        """
        Crea la relación item-impuesto de todo el lote en una sola consulta.

        Va después del `bulk_create` de items porque la relación necesita el id
        del item, que en PostgreSQL queda asignado en las instancias del propio
        `bulk_create`; no hace falta releerlas.
        """
        relaciones = [
            GenItemImpuesto(item=item, impuesto_id=impuesto_id)
            for item, impuestos in zip(items, impuestos_por_item)
            for impuesto_id in impuestos
        ]
        if relaciones:
            GenItemImpuesto.objects.bulk_create(
                relaciones, batch_size=self.BATCH_BULK_CREATE,
            )

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
    def _ids_lista(valor):
        """
        Los ids de una celda con varios separados por coma: `1,5` -> [1, 5].

        Sin validar nada: sirve para precargar. Lo que no sea un número se
        ignora acá y lo reporta `_impuestos`, que es quien valida la fila.
        """
        if valor in (None, ''):
            return []
        ids = []
        for parte in str(valor).replace(';', ',').split(','):
            parte = parte.strip()
            if not parte:
                continue
            try:
                ids.append(int(float(parte)))
            except (TypeError, ValueError):
                continue
        return ids

    @staticmethod
    def _impuestos(valor, existentes):
        """
        Los ids de impuesto de una celda, validados y sin repetir.

        La celda es opcional: un item sin impuestos es válido. Se deduplica
        porque `GenItemImpuesto` tiene `unique_together (item, impuesto)` y un
        «1,1» distraído haría fallar el lote entero con un error de base que no
        dice en qué fila estaba.
        """
        if valor in (None, ''):
            return []

        crudos = str(valor).replace(';', ',').split(',')
        ids = []
        for parte in crudos:
            parte = parte.strip()
            if not parte:
                continue
            try:
                impuesto_id = int(float(parte))
            except (TypeError, ValueError):
                raise ValueError(
                    f'Impuestos debe ser una lista de ids separados por coma, '
                    f'recibido: "{parte}"'
                )
            if impuesto_id not in existentes:
                raise ValueError(f'Impuesto con id={impuesto_id} no existe')
            if impuesto_id not in ids:
                ids.append(impuesto_id)
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

    @staticmethod
    def _texto(v):
        if v is None:
            return ''
        return str(v).strip()

    @staticmethod
    def _texto_o_none(v):
        if v is None or v == '':
            return None
        return str(v).strip()

    @staticmethod
    def _decimal(v):
        if v in (None, ''):
            return 0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
