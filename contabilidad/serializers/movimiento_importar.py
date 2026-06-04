import datetime
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from contabilidad.models import (
    ConCentroCosto,
    ConComprobante,
    ConCuenta,
    ConMovimiento,
    ConPeriodo,
)
from general.models import GenContacto, GenDocumento


class ConMovimientoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de movimientos y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = ConMovimiento
    nombre_archivo = 'movimientos'

    campos_excel = (
        ('comprobante.id', 'Comprobante'),
        ('cuenta.id', 'Cuenta'),
        ('periodo.id', 'Periodo'),
        ('numero', 'Número'),
        ('fecha', 'Fecha'),
        ('debito', 'Débito'),
        ('credito', 'Crédito'),
        ('base', 'Base'),
        ('naturaleza', 'Naturaleza'),
        ('detalle', 'Detalle'),
        ('grupo.id', 'Centro de costo'),
        ('contacto.id', 'Tercero'),
        ('documento.id', 'Documento'),
    )
    campos_requeridos = {'comprobante.id', 'cuenta.id', 'periodo.id', 'fecha', 'naturaleza'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    _FKS_OBLIGATORIOS = {
        'comprobante': ('comprobante.id', ConComprobante, 'Comprobante'),
        'cuenta': ('cuenta.id', ConCuenta, 'Cuenta'),
        'periodo': ('periodo.id', ConPeriodo, 'Periodo'),
    }
    _FKS_OPCIONALES = {
        'grupo': ('grupo.id', ConCentroCosto, 'Centro de costo'),
        'contacto': ('contacto.id', GenContacto, 'Tercero'),
        'documento': ('documento.id', GenDocumento, 'Documento'),
    }

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        todos = {**self._FKS_OBLIGATORIOS, **self._FKS_OPCIONALES}
        mapas = {
            destino: self._mapa_fk(filas_validas, campo, modelo)
            for destino, (campo, modelo, _) in todos.items()
        }

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                valores = {}
                for destino, (campo, _, etiqueta) in self._FKS_OBLIGATORIOS.items():
                    valores[destino] = self._fk_obligatorio(datos.get(campo), mapas[destino], etiqueta)
                for destino, (campo, _, etiqueta) in self._FKS_OPCIONALES.items():
                    valores[destino] = self._fk_opcional(datos.get(campo), mapas[destino], etiqueta)
                nuevos.append(ConMovimiento(
                    numero=self._entero_o_none(datos.get('numero'), 'Número'),
                    fecha=self._fecha(datos.get('fecha'), 'Fecha'),
                    debito=self._decimal(datos.get('debito'), 'Débito'),
                    credito=self._decimal(datos.get('credito'), 'Crédito'),
                    base=self._decimal(datos.get('base'), 'Base'),
                    naturaleza=self._texto(datos.get('naturaleza'))[:1],
                    detalle=self._texto_o_none(datos.get('detalle')),
                    **valores,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            ConMovimiento.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    def _mapa_fk(self, filas_validas, campo, modelo):
        ids = self._ids_int(filas_validas, campo)
        if not ids:
            return {}
        return {o.id: o for o in modelo.objects.filter(id__in=ids)}

    @staticmethod
    def _ids_int(filas_validas, campo):
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
    def _entero_o_none(v, etiqueta):
        if v is None or str(v).strip() == '':
            return None
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un entero, recibido: "{v}"')

    @staticmethod
    def _decimal(v, etiqueta, defecto=Decimal('0')):
        if v is None or str(v).strip() == '':
            return defecto
        try:
            return Decimal(str(v).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número, recibido: "{v}"')

    @staticmethod
    def _fecha(v, etiqueta):
        if isinstance(v, datetime.datetime):
            return v.date()
        if isinstance(v, datetime.date):
            return v
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es obligatoria')
        texto = str(v).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        raise ValueError(f'{etiqueta} con formato inválido: "{v}" (use AAAA-MM-DD)')
