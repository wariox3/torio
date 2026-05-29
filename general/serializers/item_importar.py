from rest_framework import serializers

from contabilidad.models import ConCuenta
from general.models import GenItem


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
    )
    campos_requeridos = {'nombre'}

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

                codigo = self._texto_o_none(datos.get('codigo'))

                if codigo is not None:
                    if codigo in vistos:
                        raise ValueError(f'El código {codigo} está duplicado dentro del archivo')
                    vistos.add(codigo)
                    if codigo in ya_existen:
                        raise ValueError(f'Ya existe un item con código {codigo}')

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
