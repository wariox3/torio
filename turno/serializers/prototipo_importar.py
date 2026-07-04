import datetime

from rest_framework import serializers

from general.models import GenDocumentoDetalle
from humano.models import HumContrato
from turno.models import TurPrototipo, TurSecuencia


class TurPrototipoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de prototipos y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = TurPrototipo
    nombre_archivo = 'prototipos'

    campos_excel = (
        ('fecha_inicio', 'Fecha inicio'),
        ('posicion', 'Posición'),
        ('contrato.id', 'Contrato'),
        ('documento_detalle.id', 'Documento detalle'),
        ('secuencia.id', 'Secuencia'),
    )
    campos_requeridos = {'fecha_inicio', 'posicion', 'contrato.id', 'documento_detalle.id', 'secuencia.id'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        mapa_contrato = self._mapa_fk(filas_validas, 'contrato.id', HumContrato)
        mapa_detalle = self._mapa_fk(filas_validas, 'documento_detalle.id', GenDocumentoDetalle)
        mapa_secuencia = self._mapa_fk(filas_validas, 'secuencia.id', TurSecuencia)

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                contrato = self._fk_obligatorio(
                    datos.get('contrato.id'), mapa_contrato, 'Contrato')
                documento_detalle = self._fk_obligatorio(
                    datos.get('documento_detalle.id'), mapa_detalle, 'Documento detalle')
                secuencia = self._fk_obligatorio(
                    datos.get('secuencia.id'), mapa_secuencia, 'Secuencia')
                nuevos.append(TurPrototipo(
                    fecha_inicio=self._fecha(datos.get('fecha_inicio'), 'Fecha inicio'),
                    posicion=self._entero(datos.get('posicion'), 'Posición'),
                    contrato=contrato,
                    documento_detalle=documento_detalle,
                    secuencia=secuencia,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            TurPrototipo.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
    def _entero(v, etiqueta):
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es obligatoria')
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número entero, recibido: "{v}"')

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
