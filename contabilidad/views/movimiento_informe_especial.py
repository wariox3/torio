from django.http import HttpResponse
from drf_spectacular.utils import OpenApiTypes, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from contabilidad.servicios import balance_excel, estado_resultados
from contabilidad.servicios.balance import CAMPOS_FILTRABLES
from contabilidad.servicios.tablero import anio_anterior
from contabilidad.views.movimiento_informe_base import InformeParametrosMixin
from utilidades.filtros import aplicar_filtros

# Registro de informes presentados sobre ConMovimiento: los que se entregan
# armados —secciones, subtotales, utilidades, comparativos— y no como filas para
# paginar. Por eso solo tienen salida en Excel.
#
# Cada informe compara el rango pedido con el mismo rango un año antes:
#
#   agrupar   (desde, hasta) → queryset agregado, sobre el que van los filtros
#   filas     (actual, anterior) → las filas del informe presentado
#   excel     (filas, empresa, desde, hasta, desde_anterior, hasta_anterior)
#             → (contenido, nombre del archivo)
INFORMES = {
    'estado_resultados_formal': {
        'agrupar': estado_resultados.agrupar,
        'filas': estado_resultados.filas,
        'excel': balance_excel.excel_estado_resultados,
    },
}

_InformeEspecialRequest = inline_serializer(
    name='InformeEspecialContabilidadRequest',
    fields={
        'informe': serializers.ChoiceField(choices=sorted(INFORMES)),
        'fecha_desde': serializers.DateField(),
        'fecha_hasta': serializers.DateField(),
        'filtros': serializers.ListField(
            child=serializers.DictField(), required=False,
            help_text='Filtros dinámicos: propiedad, operador, valor.',
        ),
    },
)


@extend_schema(tags=['Informe: Contabilidad'])
class ConMovimientoInformeEspecialViewSet(InformeParametrosMixin, viewsets.ViewSet):
    """
    Informes presentados de contabilidad, solo en Excel.

        estado_resultados_formal  el estado con secciones, subtotales y
                                  utilidades, comparado con el año anterior

        POST /excel/   { "informe": "...", "fecha_desde": "...", "fecha_hasta": "...", "filtros": [...] }

    Los `filtros` se aplican antes de agrupar y por igual a los dos cortes, el
    periodo y el mismo rango un año antes, que es contra lo que se compara. No
    acepta `ordenamientos`: el orden lo fija el informe.

    Los informes que se consultan en pantalla (balances, auxiliares, estados
    planos) están en `ConMovimientoInformeBaseViewSet`.
    """

    def _informe(self):
        clave = self._parametro('informe')
        if not clave:
            raise ValidationError({'informe': 'Este campo es requerido.'})
        if clave not in INFORMES:
            raise ValidationError(
                {'informe': f'Informe "{clave}" no existe. Opciones: {sorted(INFORMES)}.'}
            )
        return INFORMES[clave]

    @extend_schema(
        summary='Exportar a Excel',
        request=_InformeEspecialRequest,
        responses={
            (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): (
                OpenApiTypes.BINARY
            ),
        },
    )
    @action(detail=False, methods=['post'])
    def excel(self, request):
        self._rechazar_ordenamientos(request)
        informe = self._informe()
        filtros = request.data.get('filtros') or []
        desde, hasta = self._rango()
        desde_anterior, hasta_anterior = anio_anterior(desde), anio_anterior(hasta)
        filas = informe['filas'](
            aplicar_filtros(informe['agrupar'](desde, hasta), filtros, CAMPOS_FILTRABLES),
            aplicar_filtros(informe['agrupar'](desde_anterior, hasta_anterior), filtros, CAMPOS_FILTRABLES),
        )
        contenido, nombre = informe['excel'](
            filas, self._empresa(), desde, hasta, desde_anterior, hasta_anterior,
        )
        response = HttpResponse(
            contenido,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response
