from django.http import HttpResponse
from drf_spectacular.utils import OpenApiTypes, PolymorphicProxySerializer, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.formatos import FormatoSituacionFinanciera
from contabilidad.serializers import (
    ConMovimientoInformeBaseEstadoSerializer,
    ConMovimientoInformeSituacionFormalSerializer,
)
from contabilidad.servicios import balance, balance_excel
from contabilidad.servicios import situacion_financiera as sf
from contabilidad.servicios.balance import CAMPOS_FILTRABLES
from contabilidad.views.movimiento_informe_base import InformeParametrosMixin
from utilidades.filtros import aplicar_filtros
from utilidades.formatos.empresa import configuracion_actual, datos_empresa

BASE = 'base'
FORMAL = 'formal'
INFORMES = (BASE, FORMAL)

_InformeSituacionRequest = inline_serializer(
    name='InformeSituacionContabilidadRequest',
    fields={
        'informe': serializers.ChoiceField(
            choices=INFORMES,
            help_text=(
                '`base`: una fila por cuenta que movió en el rango, sin estructura. '
                '`formal`: el estado presentado, con saldos al corte y comparativo.'
            ),
        ),
        'fecha_desde': serializers.DateField(
            required=False, help_text='Solo `base`: el formal es un corte y no la usa.',
        ),
        'fecha_hasta': serializers.DateField(help_text='En `formal`, la fecha de corte.'),
        'comparar': serializers.ChoiceField(
            choices=sf.COMPARACIONES, required=False,
            help_text=(
                'Solo `formal`. `cierre_anterior` (por defecto): 31 de diciembre del año '
                'anterior. `anio_anterior`: la misma fecha un año antes. `ninguno`: sin comparativo.'
            ),
        ),
        'nivel': serializers.ChoiceField(
            choices=sf.NIVELES, required=False,
            help_text='Solo `formal`. `cuenta` (por defecto, 4 dígitos) o `grupo` (2 dígitos).',
        ),
        'filtros': serializers.ListField(
            child=serializers.DictField(), required=False,
            help_text='Filtros dinámicos: propiedad, operador, valor.',
        ),
    },
)

_EXCEL = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@extend_schema(tags=['Informe: Contabilidad'])
class ConMovimientoInformeSituacionViewSet(InformeParametrosMixin, viewsets.GenericViewSet):
    """
    Estado de situación financiera, en sus dos presentaciones.

        base     una fila por cuenta que movió en el rango, sin acotar la clase
                 (`balance.estado_situacion_financiera`), tal como sale de itrio.
                 Pide `fecha_desde` y `fecha_hasta`.
        formal   el estado presentado (`servicios.situacion_financiera`): saldos
                 acumulados a la fecha de corte (`fecha_hasta`), en secciones de
                 activo, pasivo y patrimonio con su parte corriente y no
                 corriente, el resultado del ejercicio dentro del patrimonio y un
                 corte anterior para comparar (`comparar`). `nivel` elige el
                 detalle: cuenta o grupo.

        POST /lista/   { "informe": "base" | "formal", "fecha_hasta": "...", ... }
        POST /excel/   idem
        POST /pdf/     solo `formal`

    `lista/` no pagina: `base` responde un arreglo de filas y `formal` un objeto
    con `encabezado` (empresa, cortes, totales, cuadre y razones) y `filas`.

    Los `filtros` se aplican antes de agrupar; en el formal, por igual a los dos
    cortes. Un filtro puede descuadrar el estado, y `encabezado.actual.cuadrado`
    lo dice. No acepta `ordenamientos`: sale por código de cuenta.
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

    def _opcion(self, clave, opciones, defecto):
        valor = self._parametro(clave) or defecto
        if valor not in opciones:
            raise ValidationError({clave: f'"{valor}" no es válido. Opciones: {list(opciones)}.'})
        return valor

    def _filtrar(self, queryset):
        return aplicar_filtros(queryset, self.request.data.get('filtros') or [], CAMPOS_FILTRABLES)

    def _filas_base(self):
        desde, hasta = self._rango()
        return balance.filas_estado(self._filtrar(balance.estado_situacion_financiera(desde, hasta))), desde, hasta

    def _formal(self):
        """`(filas, encabezado)` del formal."""
        corte = self._fecha('fecha_hasta')
        comparar = self._opcion('comparar', sf.COMPARACIONES, sf.CIERRE_ANTERIOR)
        nivel = self._opcion('nivel', sf.NIVELES, sf.CUENTA)
        anterior = sf.fecha_comparativo(corte, comparar)

        filas, resumen = sf.estado(
            self._filtrar(sf.agrupar(corte)),
            self._filtrar(sf.agrupar(anterior)) if anterior else None,
            nivel,
        )
        empresa = datos_empresa(configuracion_actual())
        return filas, {
            'empresa': empresa['razon_social'],
            'nit': empresa['nit'],
            'fecha_corte': corte,
            'fecha_anterior': anterior,
            'comparar': comparar,
            'nivel': nivel,
            'actual': resumen['actual'],
            'anterior': resumen['anterior'],
        }

    @extend_schema(
        request=_InformeSituacionRequest,
        responses=PolymorphicProxySerializer(
            component_name='InformeSituacionLista',
            serializers=[
                ConMovimientoInformeBaseEstadoSerializer(many=True),
                ConMovimientoInformeSituacionFormalSerializer,
            ],
            resource_type_field_name=None,
            many=False,
        ),
        description='`base` responde un arreglo de filas; `formal` un objeto con `encabezado` y `filas`.',
    )
    @action(detail=False, methods=['post'])
    def lista(self, request):
        self._rechazar_ordenamientos(request)
        if self._informe() == BASE:
            filas, _, _ = self._filas_base()
            return Response(self.get_serializer(filas, many=True).data)

        filas, encabezado = self._formal()
        return Response(ConMovimientoInformeSituacionFormalSerializer(
            {'encabezado': encabezado, 'filas': filas},
        ).data)

    @extend_schema(
        summary='Exportar a Excel',
        request=_InformeSituacionRequest,
        responses={(200, _EXCEL): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['post'])
    def excel(self, request):
        self._rechazar_ordenamientos(request)
        if self._informe() == BASE:
            filas, desde, hasta = self._filas_base()
            contenido, nombre = balance_excel.excel(
                balance_excel.ESTADO_SITUACION_FINANCIERA, filas, self._empresa(), desde, hasta,
            )
        else:
            filas, encabezado = self._formal()
            contenido, nombre = balance_excel.excel_situacion_financiera(
                filas, encabezado['empresa'], encabezado['fecha_corte'], encabezado['fecha_anterior'],
            )
        response = HttpResponse(contenido, content_type=_EXCEL)
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    @extend_schema(
        summary='Exportar a PDF',
        description='Solo `formal`: el estado listo para firmar. `base` responde 400.',
        request=_InformeSituacionRequest,
        responses={(200, 'application/pdf'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['post'])
    def pdf(self, request):
        self._rechazar_ordenamientos(request)
        if self._informe() != FORMAL:
            raise ValidationError({'informe': 'Solo el informe `formal` tiene salida en PDF.'})
        filas, encabezado = self._formal()
        contenido, nombre = FormatoSituacionFinanciera(
            filas, configuracion_actual(), encabezado['fecha_corte'], encabezado['fecha_anterior'],
        ).pdf()
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response
