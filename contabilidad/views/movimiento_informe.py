from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.models import ConMovimiento
from contabilidad.serializers import (
    ConMovimientoInformeBalanceExportarSerializer,
    ConMovimientoInformeBalanceSerializer,
    ConMovimientoInformeBalanceTotalesSerializer,
)
from contabilidad.servicios.balance import balance_prueba, totalizar
from utilidades.filtros import aplicar_filtros
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin

# Registro de informes sobre ConMovimiento.
# A diferencia de los informes de `general`, que filtran filas y declaran su
# invariante con un `Q`, acá cada informe declara cómo construir su queryset
# agrupado: lo que se sirve son totales por cuenta, no movimientos. La firma de
# `queryset` es (fecha_desde, fecha_hasta, solo_con_saldo).
INFORMES = {
    'balance_prueba': {
        'queryset': balance_prueba,
        'serializer': ConMovimientoInformeBalanceSerializer,
        'exportar': ConMovimientoInformeBalanceExportarSerializer,
    },
}

_INFORME_DEFAULT = 'balance_prueba'

_InformeRequest = inline_serializer(
    name='InformeContabilidadRequest',
    fields={
        'informe': serializers.ChoiceField(choices=sorted(INFORMES)),
        'fecha_desde': serializers.DateField(),
        'fecha_hasta': serializers.DateField(),
        'solo_con_saldo': serializers.BooleanField(
            required=False,
            help_text=(
                'Por defecto `true`: omite las cuentas sin movimiento en el rango y '
                'con saldo anterior en cero. Con `false` sale el plan completo de '
                'cuentas que alguna vez movieron.'
            ),
        ),
        'filtros': serializers.ListField(
            child=serializers.DictField(), required=False,
            help_text='Mismos filtros dinámicos de `lista`: propiedad, operador, valor.',
        ),
    },
)


@extend_schema(tags=['Informe: Contabilidad'])
class ConMovimientoInformeViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    viewsets.GenericViewSet,
):
    """
    Punto único de informes agregados sobre ConMovimiento.

    El informe se elige con el parámetro `informe` (body o query string) y el
    corte con `fecha_desde` / `fecha_hasta`, ambos obligatorios.

        POST /lista/     { "informe": "...", "fecha_desde": "...", "fecha_hasta": "...", "filtros": [...] }
        POST /excel/     idem
        POST /totales/   idem → totales de cuadre, sin paginar

    Los `filtros` se aplican antes de agrupar, así que acotan por igual el saldo
    anterior y el movimiento del rango.

    `solo_con_saldo` (por defecto `true`) omite las cuentas que no movieron en el
    rango y llegan con saldo anterior en cero.

    El informe sale siempre ordenado por código de cuenta y no acepta
    `ordenamientos`: sobre un queryset agrupado, ordenar por un campo que no
    está en el GROUP BY cambia el agrupado en silencio, y el informe devolvería
    una fila por movimiento sin que nadie lo note.
    """

    def _informe(self):
        # Generación de esquema (drf-spectacular): no hay request real, usar default.
        if getattr(self, 'swagger_fake_view', False):
            return INFORMES[_INFORME_DEFAULT]

        clave = self._parametro('informe')
        if not clave:
            raise ValidationError({'informe': 'Este campo es requerido.'})
        if clave not in INFORMES:
            raise ValidationError(
                {'informe': f'Informe "{clave}" no existe. Opciones: {sorted(INFORMES)}.'}
            )
        return INFORMES[clave]

    def _parametro(self, clave):
        request = getattr(self, 'request', None)
        if request is None:
            return None
        try:
            valor = request.data.get(clave)
        except Exception:
            valor = None
        # Comparar contra None y no por verdad: `solo_con_saldo: false` en el body
        # es un valor, no una ausencia, y con `or` se perdería.
        if valor is None:
            valor = request.query_params.get(clave)
        return valor

    def _fecha(self, clave):
        valor = self._parametro(clave)
        if not valor:
            raise ValidationError({clave: 'Este campo es requerido.'})
        try:
            return serializers.DateField().to_internal_value(valor)
        except ValidationError as error:
            raise ValidationError({clave: error.detail})

    def _rango(self):
        if getattr(self, 'swagger_fake_view', False):
            hoy = timezone.localdate()
            return hoy, hoy

        desde = self._fecha('fecha_desde')
        hasta = self._fecha('fecha_hasta')
        if desde > hasta:
            raise ValidationError({'fecha_desde': 'No puede ser posterior a `fecha_hasta`.'})
        return desde, hasta

    def _solo_con_saldo(self):
        valor = self._parametro('solo_con_saldo')
        if valor is None or valor == '':
            return True
        try:
            return serializers.BooleanField().to_internal_value(valor)
        except ValidationError as error:
            raise ValidationError({'solo_con_saldo': error.detail})

    def _rechazar_ordenamientos(self, request):
        try:
            ordenamientos = request.data.get('ordenamientos')
        except Exception:
            ordenamientos = None
        if ordenamientos:
            raise ValidationError({
                'ordenamientos': 'Este informe no acepta ordenamientos; sale por código de cuenta.',
            })

    def get_serializer_class(self):
        return self._informe()['serializer']

    def get_serializer_exportar(self):
        return self._informe()['exportar']()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ConMovimiento.objects.none()
        return self._informe()['queryset'](*self._rango(), self._solo_con_saldo())

    @extend_schema(request=_InformeRequest)
    @action(detail=False, methods=['post'])
    def lista(self, request):
        self._rechazar_ordenamientos(request)
        return super().lista(request)

    @extend_schema(request=_InformeRequest)
    @action(detail=False, methods=['post'])
    def excel(self, request):
        self._rechazar_ordenamientos(request)
        return super().excel(request)

    @extend_schema(
        summary='Totales de cuadre',
        description=(
            'Devuelve los totales del informe completo (sin paginar), sumando las '
            'mismas columnas que entrega `lista`. En un balance cuadrado, el total '
            'de débito iguala al de crédito en las tres parejas.'
        ),
        request=_InformeRequest,
        responses=ConMovimientoInformeBalanceTotalesSerializer,
    )
    @action(detail=False, methods=['post'])
    def totales(self, request):
        campos_filtrables = self._config_lista('campos_filtrables', set())
        qs = aplicar_filtros(
            self.get_queryset_lista(), request.data.get('filtros') or [], campos_filtrables,
        )
        totales = totalizar(qs.iterator(chunk_size=2000))
        return Response(ConMovimientoInformeBalanceTotalesSerializer(totales).data)
