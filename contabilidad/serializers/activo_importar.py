import datetime
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from contabilidad.models import ConActivo, ConActivoGrupo, ConCentroCosto, ConCuenta, ConMetodoDepreciacion


class ConActivoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de activos y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = ConActivo
    nombre_archivo = 'activos'

    campos_excel = (
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('marca', 'Marca'),
        ('serie', 'Serie'),
        ('modelo', 'Modelo'),
        ('fecha_compra', 'Fecha compra'),
        ('fecha_activacion', 'Fecha activación'),
        ('duracion', 'Duración'),
        ('valor_compra', 'Valor compra'),
        ('depreciacion_inicial', 'Depreciación inicial'),
        ('activo_grupo.id', 'Grupo activo'),
        ('metodo_depreciacion.id', 'Método depreciación'),
        ('cuenta_gasto.id', 'Cuenta gasto'),
        ('cuenta_depreciacion.id', 'Cuenta depreciación'),
        ('centro_costo.id', 'Centro de costo'),
    )
    campos_requeridos = {
        'codigo', 'nombre', 'fecha_compra', 'fecha_activacion',
        'activo_grupo.id', 'metodo_depreciacion.id',
        'cuenta_gasto.id', 'cuenta_depreciacion.id', 'centro_costo.id',
    }

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    _FKS = {
        'activo_grupo': ('activo_grupo.id', ConActivoGrupo, 'Grupo activo'),
        'metodo_depreciacion': ('metodo_depreciacion.id', ConMetodoDepreciacion, 'Método depreciación'),
        'cuenta_gasto': ('cuenta_gasto.id', ConCuenta, 'Cuenta gasto'),
        'cuenta_depreciacion': ('cuenta_depreciacion.id', ConCuenta, 'Cuenta depreciación'),
        'centro_costo': ('centro_costo.id', ConCentroCosto, 'Centro de costo'),
    }

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        mapas = {
            destino: self._mapa_fk(filas_validas, campo, modelo)
            for destino, (campo, modelo, _) in self._FKS.items()
        }

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                valores = {
                    destino: self._fk_obligatorio(datos.get(campo), mapas[destino], etiqueta)
                    for destino, (campo, _, etiqueta) in self._FKS.items()
                }
                nuevos.append(ConActivo(
                    codigo=self._texto(datos.get('codigo')),
                    nombre=self._texto(datos.get('nombre')),
                    marca=self._texto_o_none(datos.get('marca')),
                    serie=self._texto_o_none(datos.get('serie')),
                    modelo=self._texto_o_none(datos.get('modelo')),
                    fecha_compra=self._fecha(datos.get('fecha_compra'), 'Fecha compra'),
                    fecha_activacion=self._fecha(datos.get('fecha_activacion'), 'Fecha activación'),
                    duracion=self._entero_o_none(datos.get('duracion'), 'Duración'),
                    valor_compra=self._decimal(datos.get('valor_compra'), 'Valor compra'),
                    depreciacion_inicial=self._decimal(datos.get('depreciacion_inicial'), 'Depreciación inicial'),
                    **valores,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            ConActivo.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
