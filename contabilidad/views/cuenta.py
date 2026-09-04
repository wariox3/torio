from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from contabilidad.models import ConCuenta, ConMovimiento
from contabilidad.serializers import (
    ConCuentaExportarSerializer,
    ConCuentaImportarSerializer,
    ConCuentaSeleccionarSerializer,
    ConCuentaSerializer,
)
from general.models import GenDocumentoDetalle
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion


class ConCuentaTrasladarRequestSerializer(serializers.Serializer):
    cuenta_origen = serializers.PrimaryKeyRelatedField(queryset=ConCuenta.objects.all())
    cuenta_destino = serializers.PrimaryKeyRelatedField(queryset=ConCuenta.objects.all())

    def validate(self, attrs):
        if attrs['cuenta_origen'] == attrs['cuenta_destino']:
            raise serializers.ValidationError({'detail': 'Las cuentas no pueden ser iguales'})
        if not attrs['cuenta_destino'].permite_movimiento:
            raise serializers.ValidationError(
                {'detail': 'La cuenta destino no permite movimiento'}
            )
        return attrs

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
    OpenApiParameter('exige_base', bool, description='Filtrar por exige base'),
    OpenApiParameter('exige_contacto', bool, description='Filtrar por exige contacto'),
    OpenApiParameter('exige_centro_costo', bool, description='Filtrar por exige centro de costo'),
    OpenApiParameter('permite_movimiento', bool, description='Filtrar por permite movimiento'),
]

_UsoResponse = inline_serializer(
    name='CuentaUsoResponse',
    fields={'uso': serializers.BooleanField()},
)

_TrasladarResponse = inline_serializer(
    name='CuentaTrasladarResponse',
    fields={
        'movimientos': serializers.IntegerField(),
        'documentos_detalles': serializers.IntegerField(),
    },
)

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
]


@extend_schema(tags=['Cuenta'])
class ConCuentaViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ConCuentaSerializer
    serializer_class_exportar = ConCuentaExportarSerializer
    serializer_class_importar = ConCuentaImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = ConCuenta.objects.select_related(
            'cuenta_clase', 'cuenta_grupo', 'cuenta_cuenta', 'cuenta_subcuenta',
        ).order_by('codigo')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)

        for filtro in ('exige_base', 'exige_contacto', 'exige_centro_costo', 'permite_movimiento'):
            valor = self.request.query_params.get(filtro)
            if valor is not None:
                qs = qs.filter(**{filtro: valor.lower() == 'true'})

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConCuentaSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConCuenta.objects.order_by('codigo')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConCuentaSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Saber si la cuenta ya está en uso',
        description='Indica si algún movimiento contable referencia a la cuenta.',
        responses=_UsoResponse,
    )
    @action(detail=True, methods=['get'], url_path='validar-uso')
    def validar_uso(self, request, pk=None):
        # Sin get_object(): no hace falta traer la cuenta, solo preguntar por la FK.
        uso = ConMovimiento.objects.filter(cuenta_id=pk).exists()
        return Response({'uso': uso})

    @extend_schema(
        summary='Trasladar los movimientos de una cuenta a otra',
        description=(
            'Reasigna a la cuenta destino los movimientos contables y los detalles de '
            'documento que hoy apuntan a la cuenta origen, y devuelve cuántos registros '
            'se movieron en cada uno. La cuenta destino debe permitir movimiento. '
            'La cuenta origen no se elimina.'
        ),
        request=ConCuentaTrasladarRequestSerializer,
        responses=_TrasladarResponse,
    )
    @action(detail=False, methods=['post'])
    def trasladar(self, request):
        serializer = ConCuentaTrasladarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cuenta_origen = serializer.validated_data['cuenta_origen']
        cuenta_destino = serializer.validated_data['cuenta_destino']

        # Las dos actualizaciones son un solo traslado: o se mueve todo o no se mueve nada.
        with transaction.atomic():
            movimientos = ConMovimiento.objects.filter(
                cuenta=cuenta_origen,
            ).update(cuenta=cuenta_destino)
            documentos_detalles = GenDocumentoDetalle.objects.filter(
                cuenta=cuenta_origen,
            ).update(cuenta=cuenta_destino)

        return Response({
            'movimientos': movimientos,
            'documentos_detalles': documentos_detalles,
        })
