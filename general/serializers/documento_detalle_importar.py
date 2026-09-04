"""
Importación de detalles sobre un documento existente.

Este importador no sigue el contrato plano de los otros 35: `GenDocumentoDetalle`
es un modelo tipo `D` (detalle) y sus filas no existen por fuera de su documento.
De ahí las tres diferencias:

  * **El padre lo fija el front, nunca el Excel.** Tanto `importar-ejemplo` como
    `importar` reciben `documento=<id>`, y el padre se valida (existe, es
    modificable) antes de mirar el archivo.
  * **Las columnas dependen del `documento_tipo` del padre.** No se llena igual
    una factura que un asiento contable; `PERFIL_POR_TIPO` decide cuál aplica y
    un tipo sin perfil se rechaza en vez de importar columnas que no le sirven.
  * **No hay `bulk_create`.** Cada fila pasa por `crear_detalle()` —la misma
    puerta que usan el POST y el `masivo` del ViewSet— porque hay que sincronizar
    impuestos y llamar `calcular()` con el PK ya asignado. Al cierre se
    recalculan los totales del documento, que es justamente lo que un
    `bulk_create` dejaría desfasado.
"""
from decimal import Decimal, InvalidOperation

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from contabilidad.models import ConCentroCosto, ConCuenta
from general.models import (
    GenContacto,
    GenDocumento,
    GenDocumentoDetalle,
    GenImpuesto,
    GenItem,
)
from general.servicios.documento_detalle import crear_detalle


# ---------------------------------------------------------------- helpers ----

def _texto_o_none(valor):
    if valor is None or str(valor).strip() == '':
        return None
    return str(valor).strip()


def _decimal(valor, etiqueta, defecto=Decimal('0')):
    if valor is None or str(valor).strip() == '':
        return defecto
    try:
        return Decimal(str(valor).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{etiqueta} debe ser un número (recibido: "{valor}")')


def _decimal_obligatorio(valor, etiqueta):
    if valor is None or str(valor).strip() == '':
        raise ValueError(f'{etiqueta} es obligatorio')
    return _decimal(valor, etiqueta)


def _entero_o_none(valor, etiqueta):
    if valor is None or str(valor).strip() == '':
        return None
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        raise ValueError(f'{etiqueta} debe ser un número entero (recibido: "{valor}")')


def _ids_int(filas_validas, campo):
    """Conjunto de ids enteros presentes en `campo`. Los inválidos ya los filtró la fase 1."""
    ids = set()
    for _, datos in filas_validas:
        valor = datos.get(campo)
        if valor in (None, ''):
            continue
        try:
            ids.add(int(valor))
        except (TypeError, ValueError):
            pass
    return ids


def _mapa_fk(filas_validas, campo, modelo):
    ids = _ids_int(filas_validas, campo)
    if not ids:
        return {}
    return {o.id: o for o in modelo.objects.filter(id__in=ids)}


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


def _fk_obligatorio(valor, mapa, etiqueta):
    obj = _fk_opcional(valor, mapa, etiqueta)
    if obj is None:
        raise ValueError(f'{etiqueta} es obligatorio')
    return obj


def _ids_impuestos(valor):
    """
    Parsea la columna de impuestos: ids separados por coma.

    Excel devuelve un int cuando la celda trae un solo id ("3" se lee como 3),
    así que se normaliza a texto antes de partir.
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
            raise ValueError(f'Impuestos debe ser una lista de ids separados por coma (recibido: "{valor}")')
    return ids


# --------------------------------------------------------------- perfiles ----

class _Perfil:
    """
    Un perfil es la forma que toma el Excel para una familia de documentos:
    qué columnas trae, cuáles son obligatorias, qué se precarga de la BD y cómo
    se arma cada detalle.

    `construir` devuelve el dict de campos que recibe `crear_detalle()`; lanza
    `ValueError` con el mensaje que verá el usuario si la fila no sirve.
    """

    nombre = ''
    campos_excel = ()
    campos_requeridos = frozenset()
    valores_ejemplo = {}

    def precargar(self, filas_validas):
        return {}

    def construir(self, datos, mapas):
        raise NotImplementedError


class _PerfilComercial(_Perfil):
    """
    Venta y compra: la línea es un item con cantidad y precio. `calcular()` hace
    el resto (subtotal, descuento, impuestos, total).

    Venta y compra comparten columnas y solo difieren en qué impuestos admiten,
    de ahí `campo_impuesto`.
    """

    campo_impuesto = None  # 'venta' | 'compra' — bandera exigida en GenImpuesto

    campos_excel = (
        ('item.id', 'Item'),
        ('cantidad', 'Cantidad'),
        ('precio', 'Precio'),
        ('porcentaje_descuento', 'Porcentaje descuento'),
        ('centro_costo.id', 'Centro de costo'),
        ('detalle', 'Detalle'),
        ('impuestos', 'Impuestos separados por coma'),
    )
    campos_requeridos = frozenset({'item.id', 'cantidad', 'precio'})
    valores_ejemplo = {'impuestos': ('1,2', '')}

    def precargar(self, filas_validas):
        ids_impuesto = set()
        for _, datos in filas_validas:
            # Un valor mal formado se reporta después, fila por fila.
            try:
                ids_impuesto.update(_ids_impuestos(datos.get('impuestos')))
            except ValueError:
                continue
        impuestos = GenImpuesto.objects.filter(id__in=ids_impuesto) if ids_impuesto else []
        return {
            'item': _mapa_fk(filas_validas, 'item.id', GenItem),
            'centro_costo': _mapa_fk(filas_validas, 'centro_costo.id', ConCentroCosto),
            'impuesto': {o.id: o for o in impuestos},
        }

    def construir(self, datos, mapas):
        impuestos = []
        for pk in _ids_impuestos(datos.get('impuestos')):
            impuesto = mapas['impuesto'].get(pk)
            if impuesto is None:
                raise ValueError(f'Impuesto con id={pk} no existe')
            # El impuesto de venta no aplica en un documento de compra y viceversa:
            # dejarlo pasar arma un total que la DIAN después rechaza.
            if not getattr(impuesto, self.campo_impuesto):
                raise ValueError(
                    f'El impuesto {impuesto.nombre} no aplica a documentos de {self.nombre}'
                )
            impuestos.append(impuesto)

        return {
            'item': _fk_obligatorio(datos.get('item.id'), mapas['item'], 'Item'),
            'centro_costo': _fk_opcional(
                datos.get('centro_costo.id'), mapas['centro_costo'], 'Centro de costo',
            ),
            'cantidad': _decimal_obligatorio(datos.get('cantidad'), 'Cantidad'),
            'precio': _decimal_obligatorio(datos.get('precio'), 'Precio'),
            'porcentaje_descuento': _decimal(
                datos.get('porcentaje_descuento'), 'Porcentaje descuento',
            ),
            'detalle': _texto_o_none(datos.get('detalle')),
            'impuestos_ids': impuestos,
        }


class _PerfilVenta(_PerfilComercial):
    nombre = 'venta'
    campo_impuesto = 'venta'


class _PerfilCompra(_PerfilComercial):
    nombre = 'compra'
    campo_impuesto = 'compra'


class _PerfilContable(_Perfil):
    """
    Asiento, depreciación y cierre: la línea es un apunte contra una cuenta.

    Las columnas son las mismas de `ConMovimientoImportarSerializer` —el otro
    importador contable del proyecto— menos las que acá las pone el padre
    (comprobante, periodo, fecha y el documento mismo). El contador llena débito
    y crédito, no una naturaleza y un valor.

    `GenDocumentoDetalle` no tiene columnas `debito`/`credito` como
    `ConMovimiento`, así que el par se traduce al guardar: el lado va en
    `naturaleza` y el monto en `precio` con `cantidad = 1`, que es lo que
    `calcular()` necesita para dejar `subtotal` y `total` en el valor del apunte.
    """

    nombre = 'contable'

    campos_excel = (
        ('numero', 'Número'),
        ('cuenta.id', 'Cuenta'),
        ('contacto.id', 'Tercero'),
        ('centro_costo.id', 'Centro de costo'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('base', 'Base'),
        ('detalle', 'Detalle'),
    )
    # Débito y crédito no se exigen por separado —una celda vacía vale cero—;
    # lo que se valida es el par, en `construir`.
    campos_requeridos = frozenset({'cuenta.id'})
    # `debito` y `credito` no son campos del modelo, así que el ejemplo no se
    # puede derivar: se muestra un par cuadrado.
    valores_ejemplo = {'debito': (15000, 0), 'credito': (0, 15000)}

    def precargar(self, filas_validas):
        return {
            'cuenta': _mapa_fk(filas_validas, 'cuenta.id', ConCuenta),
            'centro_costo': _mapa_fk(filas_validas, 'centro_costo.id', ConCentroCosto),
            'contacto': _mapa_fk(filas_validas, 'contacto.id', GenContacto),
        }

    def construir(self, datos, mapas):
        cuenta = _fk_obligatorio(datos.get('cuenta.id'), mapas['cuenta'], 'Cuenta')
        # Las cuentas de agrupación (clase, grupo, mayor) no reciben movimiento:
        # importar contra ellas descuadra los informes del periodo.
        if not cuenta.permite_movimiento:
            raise ValueError(f'La cuenta {cuenta.codigo} no permite movimientos')

        naturaleza, valor = self._lado(datos)

        return {
            'cuenta': cuenta,
            'centro_costo': _fk_opcional(
                datos.get('centro_costo.id'), mapas['centro_costo'], 'Centro de costo',
            ),
            'contacto': _fk_opcional(datos.get('contacto.id'), mapas['contacto'], 'Tercero'),
            'numero': _entero_o_none(datos.get('numero'), 'Número'),
            'naturaleza': naturaleza,
            'cantidad': Decimal('1'),
            'precio': valor,
            'base': _decimal(datos.get('base'), 'Base'),
            'detalle': _texto_o_none(datos.get('detalle')),
        }

    @staticmethod
    def _lado(datos):
        """Traduce el par débito/crédito del Excel a (naturaleza, valor)."""
        debito = _decimal(datos.get('debito'), 'Débito')
        credito = _decimal(datos.get('credito'), 'Crédito')

        for etiqueta, valor in (('Débito', debito), ('Crédito', credito)):
            if valor < 0:
                raise ValueError(f'{etiqueta} no puede ser negativo (recibido: {valor})')

        if debito and credito:
            raise ValueError('Una línea no puede tener Débito y Crédito a la vez')
        if not debito and not credito:
            raise ValueError('La línea debe tener Débito o Crédito mayor que cero')

        return ('D', debito) if debito else ('C', credito)


PERFIL_VENTA = _PerfilVenta()
PERFIL_COMPRA = _PerfilCompra()
PERFIL_CONTABLE = _PerfilContable()

# Mapa explícito documento_tipo -> perfil. Los ids son los de
# `general/fixtures/11_documento_tipo.json`, que es lo que siembra cada tenant.
#
# Un tipo que no esté acá no se importa: es preferible un 400 explícito a
# ofrecer una plantilla con columnas que no corresponden a ese documento. Los
# que faltan tienen detalles con otra forma y se agregan cuando se definan:
#   - PAGO / EGRESO / SALDO INICIAL CXC / CXP: la línea cruza cartera contra
#     otro detalle (`documento_detalle_afectado`), no es un item ni un apunte.
#   - ENTRADA / SALIDA / TRASLADO ALMACEN: mueven inventario y necesitan almacén.
#   - NOMINA y familia (prima, cesantía, liquidación, seguridad social): las
#     genera la liquidación de `humano`, no se cargan a mano.
PERFIL_POR_TIPO = {
    1: PERFIL_VENTA,      # FACTURA ELECTRÓNICA DE VENTA
    2: PERFIL_VENTA,      # NOTA CRÉDITO DE VENTA
    3: PERFIL_VENTA,      # NOTA DÉBITO DE VENTA
    16: PERFIL_VENTA,     # FACTURA VENTA RECURRENTE
    17: PERFIL_VENTA,     # CUENTA COBRO
    24: PERFIL_VENTA,     # FACTURA POS ELECTRONICO
    26: PERFIL_VENTA,     # PEDIDO CLIENTE
    27: PERFIL_VENTA,     # FACTURA POS
    29: PERFIL_VENTA,     # REMISION
    30: PERFIL_VENTA,     # DEVOLUCION REMISION
    34: PERFIL_VENTA,     # CONTRATO SERVICIO
    35: PERFIL_VENTA,     # PEDIDO SERVICIO

    5: PERFIL_COMPRA,     # COMPRA
    6: PERFIL_COMPRA,     # NOTA CREDITO COMPRA
    7: PERFIL_COMPRA,     # NOTA DEBITO COMPRA
    11: PERFIL_COMPRA,    # DOCUMENTO SOPORTE
    12: PERFIL_COMPRA,    # NOTA AJUSTE
    32: PERFIL_COMPRA,    # FACTURA COMPRA RECURRENTE

    13: PERFIL_CONTABLE,  # ASIENTO
    23: PERFIL_CONTABLE,  # DEPRECIACION
    25: PERFIL_CONTABLE,  # CIERRE CONTABLE
}


# ------------------------------------------------------------- serializer ----

class GenDocumentoDetalleImportarSerializer(serializers.Serializer):
    """
    Es consumido por `ImportarExcelMixin`, pero se construye con el documento
    padre en vez de sin argumentos: es el ViewSet quien lo resuelve desde el
    parámetro `documento` y lo inyecta (ver `GenDocumentoDetalleViewSet`).

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        valores_ejemplo:      dict[campo, (fila1, fila2)]  (opcional)
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenDocumentoDetalle

    LIMITE_ERRORES = 100

    def __init__(self, documento, **kwargs):
        super().__init__(**kwargs)
        self.documento = documento
        self.perfil = self.perfil_de(documento)
        self.nombre_archivo = f'documento_{documento.id}_detalles'

    @staticmethod
    def perfil_de(documento):
        perfil = PERFIL_POR_TIPO.get(documento.documento_tipo_id)
        if perfil is None:
            raise ValidationError(
                f'El tipo de documento "{documento.documento_tipo}" no admite '
                f'importación de detalles.'
            )
        return perfil

    @property
    def campos_excel(self):
        return self.perfil.campos_excel

    @property
    def campos_requeridos(self):
        return self.perfil.campos_requeridos

    @property
    def valores_ejemplo(self):
        return self.perfil.valores_ejemplo

    def procesar_lote(self, filas_validas):
        """
        Corre dentro del `transaction.atomic()` del mixin, que revierte todo si
        se devuelve algún error.

        A diferencia de los otros importadores, acá se escribe fila por fila
        (`crear_detalle` necesita el PK para los impuestos y para `calcular()`),
        y al final se recalculan los totales del padre.
        """
        if not filas_validas:
            return 0, []

        # El padre se relee bloqueado: entre validarlo en el ViewSet y llegar acá
        # pudo aprobarse o contabilizarse en otra petición.
        try:
            documento = GenDocumento.objects.select_for_update().get(pk=self.documento.pk)
        except GenDocumento.DoesNotExist:
            return 0, [{'mensaje': 'El documento ya no existe.'}]
        if not documento.es_mutable():
            return 0, [{'mensaje': 'El documento no es modificable.'}]

        mapas = self.perfil.precargar(filas_validas)

        errores = []
        creados = 0
        for idx, datos in filas_validas:
            try:
                campos = self.perfil.construir(datos, mapas)
            except ValueError as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break
                continue
            try:
                crear_detalle(documento, campos)
            except Exception as e:
                # Un error de BD deja la transacción inutilizable, así que acá se
                # corta en vez de seguir recolectando errores como arriba.
                errores.append({'fila': idx, 'mensaje': str(e)})
                break
            creados += 1

        if errores:
            return 0, errores

        documento.recalcular_totales()
        documento.save()
        return creados, []
