import datetime
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from humano.models import HumContrato, HumNovedad, HumNovedadTipo
from humano.servicios import novedad as servicio_novedad
from humano.servicios.nomina import NOVEDAD_TIPO_VACACION


class HumNovedadImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de novedades y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])

    Cada novedad se liquida antes de crearla (`servicios.novedad.calcular`), con
    las mismas reglas que la API: sin eso pagaría cero en la nómina. Por eso no
    hay columnas de días ni de prórroga: se calculan, y el importar no maneja
    prórrogas (no tiene novedad de referencia).
    """

    model = HumNovedad
    nombre_archivo = 'novedades'

    campos_excel = (
        ('contrato.id', 'Contrato'),
        ('novedad_tipo.id', 'Tipo novedad'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('dias_disfrutados', 'Días disfrutados'),
        ('dias_disfrutados_reales', 'Días disfrutados reales'),
        ('dias_dinero', 'Días dinero'),
        ('base_cotizacion_propuesto', 'Base cotización propuesta'),
        ('detalle', 'Detalle'),
    )
    campos_requeridos = {'contrato.id', 'novedad_tipo.id', 'fecha_desde', 'fecha_hasta'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        try:
            configuracion = servicio_novedad.cargar_configuracion()
        except servicio_novedad.NovedadError as e:
            return 0, [{'fila': None, 'mensaje': e.detail}]

        mapa_contrato = self._mapa_fk(filas_validas, 'contrato.id', HumContrato)
        mapa_novedad_tipo = self._mapa_fk(
            filas_validas, 'novedad_tipo.id',
            HumNovedadTipo.objects.select_related('concepto', 'concepto2'),
        )
        # Rangos ya ocupados por empleado: los de la base y los de filas anteriores
        # del mismo archivo. Un empleado no tiene dos novedades el mismo día.
        contactos = {contrato.contacto_id for contrato in mapa_contrato.values()}
        ocupados = {}
        for contacto_id, desde, hasta in HumNovedad.objects.filter(
            contrato__contacto_id__in=contactos,
        ).values_list('contrato__contacto_id', 'fecha_desde', 'fecha_hasta'):
            ocupados.setdefault(contacto_id, []).append((desde, hasta, None))

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                contrato = self._fk_obligatorio(datos.get('contrato.id'), mapa_contrato, 'Contrato')
                novedad_tipo = self._fk_obligatorio(datos.get('novedad_tipo.id'), mapa_novedad_tipo, 'Tipo novedad')
                novedad = HumNovedad(
                    fecha_desde=self._fecha(datos.get('fecha_desde'), 'Fecha desde'),
                    fecha_hasta=self._fecha(datos.get('fecha_hasta'), 'Fecha hasta'),
                    dias_disfrutados=self._decimal(datos.get('dias_disfrutados'), 'Días disfrutados'),
                    dias_disfrutados_reales=self._decimal(
                        datos.get('dias_disfrutados_reales'), 'Días disfrutados reales',
                    ),
                    dias_dinero=self._decimal(datos.get('dias_dinero'), 'Días dinero'),
                    base_cotizacion_propuesto=self._decimal(
                        datos.get('base_cotizacion_propuesto'), 'Base cotización propuesta',
                    ),
                    detalle=self._texto_o_none(datos.get('detalle')),
                    contrato=contrato,
                    novedad_tipo=novedad_tipo,
                )
                if novedad.fecha_desde > novedad.fecha_hasta:
                    raise ValueError('La fecha desde no puede ser mayor que la fecha hasta')
                if novedad_tipo.id == NOVEDAD_TIPO_VACACION and novedad.dias_disfrutados_reales <= 0:
                    raise ValueError('Las vacaciones necesitan días disfrutados reales mayores que cero')
                for desde, hasta, fila in ocupados.get(contrato.contacto_id, ()):
                    if desde <= novedad.fecha_hasta and hasta >= novedad.fecha_desde:
                        con = f'la fila {fila}' if fila else 'otra novedad del empleado'
                        raise ValueError(f'El rango de fechas se cruza con {con}')
                servicio_novedad.calcular(novedad, configuracion)
                ocupados.setdefault(contrato.contacto_id, []).append(
                    (novedad.fecha_desde, novedad.fecha_hasta, idx),
                )
                nuevos.append(novedad)
            except servicio_novedad.NovedadError as e:
                errores.append({'fila': idx, 'mensaje': e.detail})
                if len(errores) >= self.LIMITE_ERRORES:
                    break
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            HumNovedad.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    def _mapa_fk(self, filas_validas, campo, modelo):
        """`modelo` es la clase o un queryset (para traer relaciones de una vez)."""
        ids = self._ids_int(filas_validas, campo)
        if not ids:
            return {}
        queryset = modelo.objects.all() if isinstance(modelo, type) else modelo
        return {o.id: o for o in queryset.filter(id__in=ids)}

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
