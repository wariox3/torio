import datetime

from rest_framework import serializers

from humano.models import HumAporte, HumSucursal


class HumAporteImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de aportes y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = HumAporte
    nombre_archivo = 'aportes'

    campos_excel = (
        ('anio', 'Año'),
        ('mes', 'Mes'),
        ('presentacion', 'Presentación'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('fecha_hasta_periodo', 'Fecha hasta periodo'),
        ('sucursal.id', 'Sucursal'),
        ('comentario', 'Comentario'),
    )
    campos_requeridos = {'anio', 'mes'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        mapa_sucursal = self._mapa_fk(filas_validas, 'sucursal.id', HumSucursal)

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                sucursal = self._fk_opcional(datos.get('sucursal.id'), mapa_sucursal, 'Sucursal')
                nuevos.append(HumAporte(
                    anio=self._entero(datos.get('anio'), 'Año'),
                    mes=self._entero(datos.get('mes'), 'Mes'),
                    presentacion=self._texto(datos.get('presentacion'), defecto='S')[:1] or 'S',
                    fecha_desde=self._fecha(datos.get('fecha_desde'), 'Fecha desde'),
                    fecha_hasta=self._fecha(datos.get('fecha_hasta'), 'Fecha hasta'),
                    fecha_hasta_periodo=self._fecha(datos.get('fecha_hasta_periodo'), 'Fecha hasta periodo'),
                    comentario=self._texto_o_none(datos.get('comentario')),
                    sucursal=sucursal,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            HumAporte.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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

    @staticmethod
    def _texto(v, defecto=''):
        if v is None or str(v).strip() == '':
            return defecto
        return str(v).strip()

    @staticmethod
    def _texto_o_none(v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()

    @staticmethod
    def _entero(v, etiqueta, defecto=0):
        if v is None or str(v).strip() == '':
            return defecto
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un entero, recibido: "{v}"')

    @staticmethod
    def _fecha(v, etiqueta):
        if isinstance(v, datetime.datetime):
            return v.date()
        if isinstance(v, datetime.date):
            return v
        if v is None or str(v).strip() == '':
            return None
        texto = str(v).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        raise ValueError(f'{etiqueta} con formato inválido: "{v}" (use AAAA-MM-DD)')
