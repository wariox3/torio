from django.http import HttpResponse
from drf_spectacular.utils import OpenApiTypes, PolymorphicProxySerializer, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.serializers import (
    ConMovimientoInformeBaseEstadoSerializer,
    ConMovimientoInformeResultadoFormalSerializer,
)
from contabilidad.servicios import balance, balance_excel, estado_resultados
from contabilidad.servicios.balance import CAMPOS_FILTRABLES
from contabilidad.servicios.tablero import anio_anterior
from contabilidad.views.movimiento_informe_base import InformeParametrosMixin
from utilidades.filtros import aplicar_filtros

BASE = 'base'
FORMAL = 'formal'
INFORMES = (BASE, FORMAL)

_InformeResultadoRequest = inline_serializer(
    name='InformeResultadoContabilidadRequest',
    fields={
        'informe': serializers.ChoiceField(
            choices=INFORMES,
            help_text=(
                '`base`: una fila por cuenta de resultado que movió. `formal`: el '
                'estado con secciones, utilidades y el mismo rango del año anterior.'
            ),
        ),
        'fecha_desde': serializers.DateField(),
        'fecha_hasta': serializers.DateField(),
        'filtros': serializers.ListField(
            child=serializers.DictField(), required=False,
            help_text='Filtros dinámicos: propiedad, operador, valor.',
        ),
    },
)

_EXCEL = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@extend_schema(tags=['Informe: Contabilidad'])
class ConMovimientoInformeResultadoViewSet(InformeParametrosMixin, viewsets.GenericViewSet):
    """
    Estado de resultados, en sus dos presentaciones.

        base     una fila por cuenta auxiliar de resultado que movió en el rango,
                 sin estructura (`balance.estado_resultados`). Trae los asientos
                 de cierre, como los demás informes planos.
        formal   el estado presentado: secciones, subtotales, utilidades y el
                 mismo rango un año antes (`servicios.estado_resultados`). Sin
                 asientos de cierre.

        POST /lista/   { "informe": "base" | "formal", "fecha_desde": "...", "fecha_hasta": "...", "filtros": [...] }
        POST /excel/   idem

    `lista/` no pagina: `base` responde un arreglo de filas y `formal` un objeto
    con `encabezado` y `filas`, las mismas que van al Excel.

    Los `filtros` se aplican antes de agrupar; en el formal, por igual a los dos
    cortes. No acepta `ordenamientos`: sale por código de cuenta.
    """

    serializer_class = ConMovimientoInformeBaseEstadoSerializer
    # El estado se lee completo: partirlo en páginas no deja leerlo.
    pagination_class = None

    def _informe(self):
        clave = self._parametro('informe')
        if not clave:
            raise ValidationError({'informe': 'Este campo es requerido.'})
        if clave not in INFORMES:
            raise ValidationError(
                {'informe': f'Informe "{clave}" no existe. Opciones: {list(INFORMES)}.'}
            )
        return clave

    def _filtrar(self, queryset):
        return aplicar_filtros(queryset, self.request.data.get('filtros') or [], CAMPOS_FILTRABLES)

    def _filas_base(self, desde, hasta):
        return balance.filas_estado(self._filtrar(balance.estado_resultados(desde, hasta)))

    def _filas_formal(self, desde, hasta):
        """Las filas del formal y el rango anterior contra el que se comparan."""
        desde_anterior, hasta_anterior = anio_anterior(desde), anio_anterior(hasta)
        filas = estado_resultados.filas(
            self._filtrar(estado_resultados.agrupar(desde, hasta)),
            self._filtrar(estado_resultados.agrupar(desde_anterior, hasta_anterior)),
        )
        return filas, desde_anterior, hasta_anterior

    @extend_schema(
        request=_InformeResultadoRequest,
        responses=PolymorphicProxySerializer(
            component_name='InformeResultadoLista',
            serializers=[
                ConMovimientoInformeBaseEstadoSerializer(many=True),
                ConMovimientoInformeResultadoFormalSerializer,
            ],
            resource_type_field_name=None,
            many=False,
        ),
        description='`base` responde un arreglo de filas; `formal` un objeto con `encabezado` y `filas`.',
    )
    @action(detail=False, methods=['post'])
    def lista(self, request):
        self._rechazar_ordenamientos(request)
        informe = self._informe()
        desde, hasta = self._rango()
        if informe == BASE:
            return Response(self.get_serializer(self._filas_base(desde, hasta), many=True).data)

        filas, desde_anterior, hasta_anterior = self._filas_formal(desde, hasta)
        return Response(ConMovimientoInformeResultadoFormalSerializer({
            'encabezado': {
                'empresa': self._empresa(),
                'fecha_desde': desde,
                'fecha_hasta': hasta,
                'fecha_desde_anterior': desde_anterior,
                'fecha_hasta_anterior': hasta_anterior,
            },
            'filas': filas,
        }).data)

    @extend_schema(
        summary='Exportar a Excel',
        request=_InformeResultadoRequest,
        responses={(200, _EXCEL): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['post'])
    def excel(self, request):
        self._rechazar_ordenamientos(request)
        informe = self._informe()
        desde, hasta = self._rango()
        if informe == BASE:
            contenido, nombre = balance_excel.excel(
                balance_excel.ESTADO_RESULTADOS, self._filas_base(desde, hasta),
                self._empresa(), desde, hasta,
            )
        else:
            filas, desde_anterior, hasta_anterior = self._filas_formal(desde, hasta)
            contenido, nombre = balance_excel.excel_estado_resultados(
                filas, self._empresa(), desde, hasta, desde_anterior, hasta_anterior,
            )
        response = HttpResponse(contenido, content_type=_EXCEL)
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response
