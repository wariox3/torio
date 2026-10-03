from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from humano.models import HumAdicional, HumConcepto, HumContrato, HumProgramacion
from humano.models.programacion_detalle import MENSAJE_PROGRAMACION_CERRADA


class HumAdicionalImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de adicionales y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin`, construido por el ViewSet con lo que
    manda el front (ver `HumAdicionalViewSet.importar`): o son adicionales libres
    (`permanente=True`, sin programación) o son de una programación
    (`permanente=False`). El modo vale para todo el archivo y no viaja en el
    Excel: un adicional no permanente sin programación nunca lo recoge la
    liquidación, y uno permanente por error se paga en todas las nóminas.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = HumAdicional
    nombre_archivo = 'adicionales'

    campos_excel = (
        ('contrato.id', 'Contrato'),
        ('concepto.id', 'Concepto'),
        ('valor', 'Valor'),
        ('horas', 'Horas'),
        ('aplica_dia_laborado', 'Aplica día laborado'),
        ('detalle', 'Detalle'),
    )
    campos_requeridos = {'contrato.id', 'concepto.id'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def __init__(self, *, permanente, programacion=None, **kwargs):
        super().__init__(**kwargs)
        self.permanente = permanente
        self.programacion = programacion

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        programacion = None
        if self.programacion is not None:
            # Se relee bloqueada: entre validarla en el ViewSet y llegar acá pudo
            # generarse en otra petición.
            try:
                programacion = HumProgramacion.objects.select_for_update().get(pk=self.programacion.pk)
            except HumProgramacion.DoesNotExist:
                return 0, [{'mensaje': 'La programación ya no existe.'}]
            if programacion.estado_generado or programacion.estado_aprobado:
                return 0, [{'mensaje': MENSAJE_PROGRAMACION_CERRADA}]

        mapa_contrato = self._mapa_fk(filas_validas, 'contrato.id', HumContrato)
        mapa_concepto = self._mapa_fk(filas_validas, 'concepto.id', HumConcepto)

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                contrato = self._fk_obligatorio(datos.get('contrato.id'), mapa_contrato, 'Contrato')
                concepto = self._fk_obligatorio(datos.get('concepto.id'), mapa_concepto, 'Concepto')
                nuevos.append(HumAdicional(
                    valor=self._decimal(datos.get('valor'), 'Valor'),
                    horas=self._decimal(datos.get('horas'), 'Horas'),
                    aplica_dia_laborado=self._si_no(datos.get('aplica_dia_laborado')),
                    permanente=self.permanente,
                    detalle=self._texto_o_none(datos.get('detalle')),
                    programacion=programacion,
                    contrato=contrato,
                    concepto=concepto,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            HumAdicional.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
    def _texto_o_none(v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()

    @staticmethod
    def _decimal(v, etiqueta, defecto=Decimal('0')):
        if v is None or str(v).strip() == '':
            return defecto
        try:
            return Decimal(str(v).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número, recibido: "{v}"')

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
