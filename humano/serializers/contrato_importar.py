import datetime
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from contabilidad.models import ConCentroCosto
from general.models import GenCiudad, GenContacto
from humano.models import (
    HumCargo,
    HumContrato,
    HumContratoTipo,
    HumEntidad,
    HumGrupo,
    HumMotivoTerminacion,
    HumPension,
    HumRiesgo,
    HumSalud,
    HumSubtipoCotizante,
    HumSucursal,
    HumTiempo,
    HumTipoCosto,
    HumTipoCotizante,
)


class HumContratoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de contratos y la lógica de
    creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = HumContrato
    nombre_archivo = 'contratos'

    campos_excel = (
        ('contacto.id', 'Contacto'),
        ('contrato_tipo.id', 'Tipo contrato'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('salario', 'Salario'),
        ('auxilio_transporte', 'Auxilio transporte'),
        ('salario_integral', 'Salario integral'),
        ('grupo.id', 'Grupo'),
        ('sucursal.id', 'Sucursal'),
        ('cargo.id', 'Cargo'),
        ('ciudad_contrato.id', 'Ciudad contrato'),
        ('ciudad_labora.id', 'Ciudad labora'),
        ('tipo_cotizante.id', 'Tipo cotizante'),
        ('subtipo_cotizante.id', 'Subtipo cotizante'),
        ('riesgo.id', 'Riesgo'),
        ('salud.id', 'Salud'),
        ('pension.id', 'Pensión'),
        ('entidad_salud.id', 'Entidad salud'),
        ('entidad_pension.id', 'Entidad pensión'),
        ('entidad_cesantias.id', 'Entidad cesantías'),
        ('entidad_caja.id', 'Entidad caja'),
        ('tiempo.id', 'Tiempo'),
        ('tipo_costo.id', 'Tipo costo'),
        ('grupo_contabilidad.id', 'Centro de costo'),
        ('comentario', 'Comentario'),
    )
    campos_requeridos = {'contacto.id', 'contrato_tipo.id', 'fecha_desde', 'fecha_hasta', 'grupo.id'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    # campo destino -> (campo excel, modelo, etiqueta)
    _FKS = {
        'contacto': ('contacto.id', GenContacto, 'Contacto'),
        'contrato_tipo': ('contrato_tipo.id', HumContratoTipo, 'Tipo contrato'),
        'grupo': ('grupo.id', HumGrupo, 'Grupo'),
        'sucursal': ('sucursal.id', HumSucursal, 'Sucursal'),
        'cargo': ('cargo.id', HumCargo, 'Cargo'),
        'ciudad_contrato': ('ciudad_contrato.id', GenCiudad, 'Ciudad contrato'),
        'ciudad_labora': ('ciudad_labora.id', GenCiudad, 'Ciudad labora'),
        'tipo_cotizante': ('tipo_cotizante.id', HumTipoCotizante, 'Tipo cotizante'),
        'subtipo_cotizante': ('subtipo_cotizante.id', HumSubtipoCotizante, 'Subtipo cotizante'),
        'riesgo': ('riesgo.id', HumRiesgo, 'Riesgo'),
        'salud': ('salud.id', HumSalud, 'Salud'),
        'pension': ('pension.id', HumPension, 'Pensión'),
        'entidad_salud': ('entidad_salud.id', HumEntidad, 'Entidad salud'),
        'entidad_pension': ('entidad_pension.id', HumEntidad, 'Entidad pensión'),
        'entidad_cesantias': ('entidad_cesantias.id', HumEntidad, 'Entidad cesantías'),
        'entidad_caja': ('entidad_caja.id', HumEntidad, 'Entidad caja'),
        'tiempo': ('tiempo.id', HumTiempo, 'Tiempo'),
        'tipo_costo': ('tipo_costo.id', HumTipoCosto, 'Tipo costo'),
        'grupo_contabilidad': ('grupo_contabilidad.id', ConCentroCosto, 'Centro de costo'),
    }

    def procesar_lote(self, filas_validas):
        """
        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs de cada catálogo en mapas {id: instancia}
        mapas = {
            destino: self._mapa_fk(filas_validas, campo, modelo)
            for destino, (campo, modelo, _) in self._FKS.items()
        }

        # 2) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                valores = {
                    destino: self._fk_opcional(datos.get(campo), mapas[destino], etiqueta)
                    for destino, (campo, _, etiqueta) in self._FKS.items()
                }
                nuevos.append(HumContrato(
                    fecha_desde=self._fecha(datos.get('fecha_desde'), 'Fecha desde'),
                    fecha_hasta=self._fecha(datos.get('fecha_hasta'), 'Fecha hasta'),
                    salario=self._decimal(datos.get('salario'), 'Salario'),
                    auxilio_transporte=self._si_no(datos.get('auxilio_transporte')),
                    salario_integral=self._si_no(datos.get('salario_integral')),
                    comentario=self._texto_o_none(datos.get('comentario')),
                    **valores,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            HumContrato.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    def _mapa_fk(self, filas_validas, campo, modelo):
        """Pre-carga en un mapa {id: instancia} los registros referenciados por `campo`."""
        ids = self._ids_int(filas_validas, campo)
        if not ids:
            return {}
        return {o.id: o for o in modelo.objects.filter(id__in=ids)}

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
                pass  # tipos inválidos se reportan al construir la fila
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

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
