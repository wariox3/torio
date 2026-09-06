from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from general.models import GenDocumentoDetalle, GenItem
from inventario.models import InvExistencia
from inventario.serializers import (
    InvExistenciaAlmacenInformeExportarSerializer,
    InvExistenciaAlmacenInformeSerializer,
    InvExistenciaInformeExportarSerializer,
    InvExistenciaInformeSerializer,
    InvHistorialMovimientoInformeExportarSerializer,
    InvHistorialMovimientoInformeSerializer,
    InvInventarioValorizadoInformeExportarSerializer,
    InvInventarioValorizadoInformeSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin

# Registro de informes de inventario.
# Cada informe declara su invariante (`filtro`, garantizada por el servidor) y,
# opcionalmente, sus columnas con `serializer` / `exportar`.
#
# A diferencia de los otros informes planos, acá cada uno declara además su
# `modelo`: el inventario no vive en una sola tabla —el saldo consolidado está en
# `gen_item`, el desglose por almacén en `inv_existencia` y el movimiento que los
# produjo en `gen_documento_detalle`— y son tres vistas del mismo hecho, así que
# se sirven de un solo endpoint. Dos de esos modelos están en `general`, pero los
# informes son de inventario y se sirven de acá.
INFORMES = {
    'existencia': {
        'modelo': GenItem,
        # `inventario` es lo que decide si el item lleva saldo. Un servicio, o un
        # producto que no maneja inventario, tiene los tres saldos en cero para
        # siempre: meterlo en el informe solo agrega ruido.
        #
        # No se filtra por `existencia != 0` ni por `inactivo`: un item que nunca
        # movió y uno inactivo que quedó con saldo son justamente los dos casos
        # que hay que poder ver. Para acotarlos está `filtros`.
        'filtro': Q(inventario=True),
    },
    'existencia_almacen': {
        'modelo': InvExistencia,
        # La misma invariante que `existencia`, un nivel más abajo: así los dos
        # cubren el mismo universo de items y el desglose por almacén suma
        # exactamente el consolidado. Un item al que le apagaron `inventario` con
        # saldo vivo desaparece de los dos a la vez, no de uno.
        'filtro': Q(item__inventario=True),
        'serializer': InvExistenciaAlmacenInformeSerializer,
        'exportar': InvExistenciaAlmacenInformeExportarSerializer,
    },
    'inventario_valorizado': {
        'modelo': GenItem,
        # Las mismas filas de `existencia`: lo que cambia son las columnas, no la
        # invariante. Valorizar un universo distinto haría que el total del
        # informe no cuadrara contra el de existencias.
        'filtro': Q(inventario=True),
        'serializer': InvInventarioValorizadoInformeSerializer,
        'exportar': InvInventarioValorizadoInformeExportarSerializer,
    },
    'historial_movimiento': {
        'modelo': GenDocumentoDetalle,
        # Qué es "mover inventario" lo define `_afectar_inventario`, y esta
        # invariante es su espejo: línea con item y almacén, en un documento
        # aprobado, que mueva alguno de los dos saldos.
        #
        # Los tres pedazos importan. Sin `estado_aprobado` entrarían borradores
        # que nunca tocaron un saldo. Sin item o sin almacén la línea no llega al
        # servicio. Y con las dos operaciones en cero no movió nada: la de
        # remisión va aparte porque saca de disponible sin sacar de existencia, y
        # dejarla fuera perdería justamente los despachos.
        'filtro': (
            Q(item__isnull=False, almacen__isnull=False, documento__estado_aprobado=True)
            & (~Q(operacion_inventario=0) | ~Q(operacion_remision=0))
        ),
        'serializer': InvHistorialMovimientoInformeSerializer,
        'exportar': InvHistorialMovimientoInformeExportarSerializer,
    },
}

_INFORME_DEFAULT = 'existencia'


@extend_schema(tags=['Informe: Inventario'])
class InvInformeViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    viewsets.GenericViewSet,
):
    """
    Punto único de informes de inventario.

    El informe se elige con el parámetro `informe` (body o query string). Cada
    informe define en `INFORMES` su invariante (filtro garantizado por el
    servidor) y, opcionalmente, su serializer de columnas.

        POST /lista/    { "informe": "...", "filtros": [...] }
        POST /excel/    { "informe": "...", "filtros": [...] }

        existencia              una fila por item, con el saldo consolidado
        existencia_almacen      una fila por item y almacén
        inventario_valorizado   `existencia` con costo promedio y costo total
        historial_movimiento    las líneas de documento que movieron inventario

    Los tres primeros son el saldo de hoy y el cuarto es cómo se llegó a él: la
    suma de `cantidad_operada` del historial de un item reconstruye su
    `existencia`, porque las dos cosas las escribe la misma transacción en
    `general.servicios.documento._afectar_inventario`.

    Cada informe declara sus propias columnas y sus propios `campos_filtrables`
    en su serializer, así que un filtro válido para uno puede no serlo para otro:
    `existencia` filtra por `nombre` y `existencia_almacen` por `item__nombre`.
    """

    def _informe(self):
        # Generación de esquema (drf-spectacular): no hay request real, usar default.
        if getattr(self, 'swagger_fake_view', False):
            return INFORMES[_INFORME_DEFAULT]

        request = getattr(self, 'request', None)
        clave = None
        if request is not None:
            try:
                clave = request.data.get('informe')
            except Exception:
                clave = None
            if not clave:
                clave = request.query_params.get('informe')
        if not clave:
            raise ValidationError({'informe': 'Este campo es requerido.'})
        if clave not in INFORMES:
            raise ValidationError(
                {'informe': f'Informe "{clave}" no existe. Opciones: {sorted(INFORMES)}.'}
            )
        return INFORMES[clave]

    def get_serializer_class(self):
        return self._informe().get('serializer', InvExistenciaInformeSerializer)

    def get_serializer_exportar(self):
        return self._informe().get('exportar', InvExistenciaInformeExportarSerializer)()

    def get_queryset(self):
        informe = self._informe()
        return informe['modelo'].objects.filter(informe['filtro'])
