import datetime

from rest_framework import serializers

from humano.models import HumGrupo, HumPagoTipo, HumPeriodo, HumProgramacion


class HumProgramacionImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de programaciones y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = HumProgramacion
    nombre_archivo = 'programaciones'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('fecha_hasta_periodo', 'Fecha hasta periodo'),
        ('grupo.id', 'Grupo'),
        ('pago_tipo.id', 'Tipo pago'),
        ('periodo.id', 'Periodo'),
        ('comentario', 'Comentario'),
    )
    campos_requeridos = {'fecha_desde', 'fecha_hasta', 'fecha_hasta_periodo', 'grupo.id', 'pago_tipo.id'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        if not filas_validas:
            return 0, []

        mapa_grupo = self._mapa_fk(filas_validas, 'grupo.id', HumGrupo)
        mapa_pago_tipo = self._mapa_fk(filas_validas, 'pago_tipo.id', HumPagoTipo)
        mapa_periodo = self._mapa_fk(filas_validas, 'periodo.id', HumPeriodo)

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                grupo = self._fk_obligatorio(datos.get('grupo.id'), mapa_grupo, 'Grupo')
                pago_tipo = self._fk_obligatorio(datos.get('pago_tipo.id'), mapa_pago_tipo, 'Tipo pago')
                periodo = self._fk_opcional(datos.get('periodo.id'), mapa_periodo, 'Periodo')
                nuevos.append(HumProgramacion(
                    nombre=self._texto_o_none(datos.get('nombre')),
                    fecha_desde=self._fecha(datos.get('fecha_desde'), 'Fecha desde'),
                    fecha_hasta=self._fecha(datos.get('fecha_hasta'), 'Fecha hasta'),
                    fecha_hasta_periodo=self._fecha(datos.get('fecha_hasta_periodo'), 'Fecha hasta periodo'),
                    comentario=self._texto_o_none(datos.get('comentario')),
                    grupo=grupo,
                    pago_tipo=pago_tipo,
                    periodo=periodo,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            HumProgramacion.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
