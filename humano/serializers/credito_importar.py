import datetime
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from humano.models import HumConcepto, HumContrato, HumCredito


class HumCreditoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de créditos y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = HumCredito
    nombre_archivo = 'creditos'

    campos_excel = (
        ('contrato.id', 'Contrato'),
        ('concepto.id', 'Concepto'),
        ('fecha_inicio', 'Fecha inicio'),
        ('total', 'Total'),
        ('cuota', 'Cuota'),
        ('cantidad_cuotas', 'Cantidad cuotas'),
        ('validar_cuotas', 'Validar cuotas'),
        ('aplica_prima', 'Aplica prima'),
        ('aplica_cesantia', 'Aplica cesantía'),
        ('comentario', 'Comentario'),
    )
    campos_requeridos = {'contrato.id', 'fecha_inicio'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        mapa_contrato = self._mapa_fk(filas_validas, 'contrato.id', HumContrato)
        mapa_concepto = self._mapa_fk(filas_validas, 'concepto.id', HumConcepto)

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                contrato = self._fk_obligatorio(datos.get('contrato.id'), mapa_contrato, 'Contrato')
                concepto = self._fk_opcional(datos.get('concepto.id'), mapa_concepto, 'Concepto')
                total = self._decimal(datos.get('total'), 'Total')
                nuevos.append(HumCredito(
                    fecha_inicio=self._fecha(datos.get('fecha_inicio'), 'Fecha inicio'),
                    total=total,
                    cuota=self._decimal(datos.get('cuota'), 'Cuota'),
                    saldo=total,
                    cantidad_cuotas=self._entero(datos.get('cantidad_cuotas'), 'Cantidad cuotas'),
                    validar_cuotas=self._si_no(datos.get('validar_cuotas'), defecto=True),
                    aplica_prima=self._si_no(datos.get('aplica_prima')),
                    aplica_cesantia=self._si_no(datos.get('aplica_cesantia')),
                    comentario=self._texto_o_none(datos.get('comentario')),
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
            HumCredito.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
            raise ValueError(f'{etiqueta} es obligatoria')
        texto = str(v).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        raise ValueError(f'{etiqueta} con formato inválido: "{v}" (use AAAA-MM-DD)')

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
