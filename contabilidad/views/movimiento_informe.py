from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.models import ConMovimiento
from contabilidad.serializers import (
    ConMovimientoInformeAuxiliarContactoSerializer,
    ConMovimientoInformeAuxiliarCuentaSerializer,
    ConMovimientoInformeAuxiliarGeneralSerializer,
    ConMovimientoInformeBalanceContactoSerializer,
    ConMovimientoInformeBalanceSerializer,
    ConMovimientoInformeBalanceTotalesSerializer,
    ConMovimientoInformeBasesSerializer,
    ConMovimientoInformeBasesTotalesSerializer,
    ConMovimientoInformeCertificadoSerializer,
    ConMovimientoInformeCertificadoTotalesSerializer,
    ConMovimientoInformeEstadoSerializer,
    ConMovimientoInformeEstadoTotalesSerializer,
)
from contabilidad.formatos import FormatoCertificadoRetencion
from contabilidad.servicios import balance, balance_excel
from general.models import GenConfiguracion
from utilidades.filtros import aplicar_filtros
from utilidades.mixins import FiltrosDinamicosMixin

# Registro de informes sobre ConMovimiento.
# A diferencia de los informes de `general`, que filtran filas y declaran su
# invariante con un `Q`, acá cada informe se declara entero y no se programa.
# Hay dos familias y `detalle` las separa:
#
#   jerárquicos (detalle != None): `agrupar` da el agregado por cuenta que se
#       filtra en el WHERE, `movimiento` la segunda consulta cuando el detalle
#       la pide, y `balance.jerarquizar` arma la jerarquía. La aritmética y el
#       orden son los mismos para los cinco.
#   planos (detalle = None): `agrupar` da la única consulta y `filas` la
#       convierte en las filas del informe. No hay plan de cuentas que recorrer.
#
# `excel` es la forma de la tabla, que no se puede delegar en
# `ExportarExcelMixin` porque lleva bloque de título, y `totales` el serializer
# que además declara qué suma `totales/`.
INFORMES = {
    'balance_prueba': {
        'agrupar': balance.balance_prueba,
        'movimiento': None,
        'detalle': balance.SIN_DETALLE,
        'filas': None,
        'serializer': ConMovimientoInformeBalanceSerializer,
        'totales': ConMovimientoInformeBalanceTotalesSerializer,
        'excel': balance_excel.BALANCE,
    },
    'balance_prueba_contacto': {
        'agrupar': balance.balance_prueba_contacto,
        'movimiento': None,
        'detalle': balance.POR_TERCERO,
        'filas': None,
        'serializer': ConMovimientoInformeBalanceContactoSerializer,
        'totales': ConMovimientoInformeBalanceTotalesSerializer,
        'excel': balance_excel.BALANCE_CONTACTO,
    },
    'auxiliar_cuenta': {
        'agrupar': balance.balance_prueba,
        'movimiento': balance.movimientos,
        'detalle': balance.POR_MOVIMIENTO,
        'filas': None,
        'serializer': ConMovimientoInformeAuxiliarCuentaSerializer,
        'totales': ConMovimientoInformeBalanceTotalesSerializer,
        'excel': balance_excel.AUXILIAR_CUENTA,
    },
    'auxiliar_contacto': {
        'agrupar': balance.balance_prueba_contacto,
        'movimiento': balance.movimientos,
        'detalle': balance.POR_TERCERO_ANIDADO,
        'filas': None,
        'serializer': ConMovimientoInformeAuxiliarContactoSerializer,
        'totales': ConMovimientoInformeBalanceTotalesSerializer,
        'excel': balance_excel.AUXILIAR_CONTACTO,
    },
    'auxiliar_general': {
        'agrupar': balance.balance_prueba_contacto,
        'movimiento': balance.movimientos,
        'detalle': balance.POR_TERCERO_Y_MOVIMIENTO,
        'filas': None,
        'serializer': ConMovimientoInformeAuxiliarGeneralSerializer,
        'totales': ConMovimientoInformeBalanceTotalesSerializer,
        'excel': balance_excel.AUXILIAR_GENERAL,
    },
    'bases': {
        'agrupar': balance.movimientos_con_base,
        'movimiento': None,
        'detalle': None,
        'filas': balance.filas_movimiento,
        'serializer': ConMovimientoInformeBasesSerializer,
        'totales': ConMovimientoInformeBasesTotalesSerializer,
        'excel': balance_excel.BASES,
    },
    'certificado_retencion': {
        'agrupar': balance.certificado_retencion,
        'movimiento': None,
        'detalle': None,
        'filas': balance.filas_certificado,
        'serializer': ConMovimientoInformeCertificadoSerializer,
        'totales': ConMovimientoInformeCertificadoTotalesSerializer,
        'excel': balance_excel.CERTIFICADO_RETENCION,
        # Único informe con salida en PDF: el certificado es un documento que se
        # entrega al tercero, no una tabla que se consulta. Los demás informes no
        # declaran `pdf` y la acción los rechaza.
        'pdf': FormatoCertificadoRetencion,
    },
    'estado_resultados': {
        'agrupar': balance.estado_resultados,
        'movimiento': None,
        'detalle': None,
        'filas': balance.filas_estado,
        'serializer': ConMovimientoInformeEstadoSerializer,
        'totales': ConMovimientoInformeEstadoTotalesSerializer,
        'excel': balance_excel.ESTADO_RESULTADOS,
    },
    'estado_situacion_financiera': {
        'agrupar': balance.estado_situacion_financiera,
        'movimiento': None,
        'detalle': None,
        'filas': balance.filas_estado,
        'serializer': ConMovimientoInformeEstadoSerializer,
        'totales': ConMovimientoInformeEstadoTotalesSerializer,
        'excel': balance_excel.ESTADO_SITUACION_FINANCIERA,
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
                'Por defecto `false`: sale el plan de cuentas completo, incluidas '
                'las cuentas que nunca movieron. Con `true` se omiten las cuentas '
                'que quedan en ceros en las cuatro columnas, y sus terceros.'
            ),
        ),
        'filtros': serializers.ListField(
            child=serializers.DictField(), required=False,
            help_text='Mismos filtros dinámicos de `lista`: propiedad, operador, valor.',
        ),
    },
)


@extend_schema(tags=['Informe: Contabilidad'])
class ConMovimientoInformeViewSet(FiltrosDinamicosMixin, viewsets.GenericViewSet):
    """
    Punto único de informes agregados sobre ConMovimiento.

    Cinco son jerárquicos: el mismo esqueleto —el plan de cuentas con el
    movimiento de un rango— con más o menos detalle colgando de cada auxiliar.

        balance_prueba            nada
        balance_prueba_contacto   una fila TERCERO por contacto
        auxiliar_cuenta           una fila MOVIMIENTO por asiento del rango
        auxiliar_contacto         cada TERCERO seguido de sus MOVIMIENTO
        auxiliar_general          los TERCERO y después todos los MOVIMIENTO,
                                  con comprobante, número y fecha

    Los otros cuatro son planos: no recorren el plan de cuentas sino lo que pasó
    en el rango, así que no tienen jerarquía, subtotales ni `solo_con_saldo`.

        bases                     los asientos sobre cuentas que exigen base
        certificado_retencion     lo retenido a cada tercero, por cuenta
        estado_resultados         las cuentas de resultado que movieron
        estado_situacion_financiera  lo mismo sin acotar la clase

    El informe se elige con el parámetro `informe` (body o query string) y el
    corte con `fecha_desde` / `fecha_hasta`, ambos obligatorios.

        POST /lista/     { "informe": "...", "fecha_desde": "...", "fecha_hasta": "...", "filtros": [...] }
        POST /excel/     idem
        POST /totales/   idem → totales del informe completo, sin paginar

    Cada auxiliar del plan viene precedido por las filas de subtotal de su clase,
    grupo y cuenta, y el campo `tipo` dice qué es cada fila. `totales/` suma solo
    las de tipo `AUXILIAR`: tanto los subtotales como el detalle están hechos de
    ellas, así que sumarlo todo multiplicaría el balance.

    Los `filtros` se aplican antes de agrupar y sobre las dos consultas, así que
    acotan por igual el saldo anterior, el movimiento del rango y el detalle.

    Los asientos de cierre entran al saldo anterior pero no a las columnas del
    rango ni al detalle: cancelan las cuentas de resultado contra el ejercicio, y
    contarlos como movimiento del periodo duplicaría el resultado del año en la
    columna de diciembre. Los cuatro informes planos sí los traen.

    `solo_con_saldo` (por defecto `false`) omite las cuentas que quedan en ceros,
    con su detalle. En los informes planos no aplica y se ignora.

    El informe sale siempre ordenado por código de cuenta y no acepta
    `ordenamientos`: dentro de una cuenta el orden lo fija el informe —los
    terceros por contacto, los movimientos por fecha y número— y reordenar por
    encima despegaría el detalle de su cuenta.
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
            return False
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

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ConMovimiento.objects.none()
        return self._informe()['agrupar'](*self._rango())

    def _filas(self, request):
        """
        Filas jerarquizadas del informe. Es lo que sirven las tres acciones, para
        que ninguna pueda entregar un número distinto de las otras.
        """
        self._rechazar_ordenamientos(request)
        informe = self._informe()
        filtros = request.data.get('filtros') or []
        campos_filtrables = self._config_lista('campos_filtrables', set())

        agrupado = aplicar_filtros(self.get_queryset_lista(), filtros, campos_filtrables)

        detalle = informe['detalle']
        if detalle is None:
            return informe['filas'](agrupado)

        # Los mismos filtros van a las dos consultas: si solo acotaran el
        # agregado, el auxiliar mostraría un total filtrado con un detalle que no
        # lo explica.
        movimiento = ()
        if informe['movimiento'] is not None:
            movimiento = aplicar_filtros(
                informe['movimiento'](*self._rango()), filtros, campos_filtrables,
            )
        return balance.jerarquizar(agrupado, movimiento, detalle, self._solo_con_saldo())

    @extend_schema(request=_InformeRequest)
    @action(detail=False, methods=['post'])
    def lista(self, request):
        filas = self._filas(request)
        pagina = self.paginate_queryset(filas)
        return self.get_paginated_response(self.get_serializer(pagina, many=True).data)

    @extend_schema(
        summary='Exportar a Excel',
        request=_InformeRequest,
        responses={
            (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): (
                OpenApiTypes.BINARY
            ),
        },
    )
    @action(detail=False, methods=['post'])
    def excel(self, request):
        filas = self._filas(request)
        desde, hasta = self._rango()
        contenido, nombre = balance_excel.excel(
            self._informe()['excel'], filas, self._empresa(), desde, hasta,
        )
        response = HttpResponse(
            contenido,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    @extend_schema(
        summary='Exportar a PDF',
        description=(
            'Solo `certificado_retencion`: devuelve un PDF con una hoja por '
            'tercero. Los demás informes responden 400.'
        ),
        request=_InformeRequest,
        responses={(200, 'application/pdf'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['post'])
    def pdf(self, request):
        formato = self._informe().get('pdf')
        if formato is None:
            raise ValidationError({
                'informe': 'Este informe no tiene salida en PDF.',
            })
        desde, hasta = self._rango()
        contenido, nombre = formato(
            self._filas(request), self._configuracion(), desde, hasta,
        ).pdf()
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    @extend_schema(
        summary='Totales del informe',
        description=(
            'Devuelve los totales del informe completo (sin paginar), sumando las '
            'filas de tipo `AUXILIAR`. En un balance cuadrado el total de débitos '
            'iguala al de créditos y los dos saldos dan cero.'
        ),
        request=_InformeRequest,
        responses=ConMovimientoInformeBalanceTotalesSerializer,
    )
    @action(detail=False, methods=['post'])
    def totales(self, request):
        serializer = self._informe()['totales']
        totales = balance.totalizar(
            self._filas(request), serializer.tipo_fila, serializer.columnas,
        )
        return Response(serializer(totales).data)

    @staticmethod
    def _configuracion():
        """La configuración del tenant, de donde salen los datos del agente retenedor."""
        return (
            GenConfiguracion.objects
            .select_related('gen_empresa_ciudad__estado')
            .first()
        )

    @staticmethod
    def _empresa():
        """Razón social para el encabezado del Excel; vacía si el tenant no la configuró."""
        configuracion = GenConfiguracion.objects.first()
        return configuracion.gen_empresa_razon_social if configuracion else ''
