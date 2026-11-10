from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from contabilidad.models import ConMovimiento
from contabilidad.serializers import (
    ConMovimientoExportarSerializer,
    ConMovimientoImportarSerializer,
    ConMovimientoSeleccionarSerializer,
    ConMovimientoSerializer,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por detalle o cuenta'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por cuenta'),
]

_ELIMINADOS_RESPONSE = inline_serializer(
    name='MovimientoEliminadosResponse',
    fields={'eliminados': serializers.IntegerField()},
)

@extend_schema(tags=['Movimiento'])
class ConMovimientoViewSet(
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
    serializer_class = ConMovimientoSerializer
    serializer_class_exportar = ConMovimientoExportarSerializer
    serializer_class_importar = ConMovimientoImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = ConMovimiento.objects.select_related(
            *ConMovimientoSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = (
                qs.filter(detalle__icontains=search)
                | qs.filter(cuenta__nombre__icontains=search)
                | qs.filter(cuenta__codigo__icontains=search)
            )

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConMovimientoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConMovimiento.objects.select_related('cuenta').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(cuenta__nombre__icontains=search) | qs.filter(cuenta__codigo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConMovimientoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Eliminar saldo inicial',
        description=(
            'Elimina todos los movimientos de saldo inicial de un comprobante y número. '
            'Se borra el asiento completo para no dejar la contabilidad descuadrada. '
            'Si alguno está en un periodo bloqueado, no se elimina ninguno.'
        ),
        request=inline_serializer(
            name='MovimientoEliminarMasivoRequest',
            fields={
                'comprobante_id': serializers.IntegerField(),
                'numero': serializers.IntegerField(),
            },
        ),
        responses=_ELIMINADOS_RESPONSE,
    )
    @action(detail=False, methods=['post'], url_path='eliminar-masivo')
    def eliminar_masivo(self, request):
        valores = {}
        for campo in ('comprobante_id', 'numero'):
            valor = request.data.get(campo)
            if valor in (None, ''):
                raise ValidationError({'detail': f'{campo} es obligatorio.'})
            try:
                valores[campo] = int(valor)
            except (TypeError, ValueError):
                raise ValidationError({'detail': f'{campo} debe ser un entero.'})

        with transaction.atomic():
            movimientos = list(
                ConMovimiento.objects.select_for_update()
                .filter(saldo_inicial=True, **valores)
                .values_list('id', 'periodo_id', 'periodo__estado_bloqueado')
            )
            if not movimientos:
                raise ValidationError({
                    'detail': (
                        f'No hay movimientos de saldo inicial del comprobante '
                        f'{valores["comprobante_id"]} número {valores["numero"]}.'
                    ),
                })
            bloqueados = sorted({periodo_id for _, periodo_id, bloqueado in movimientos if bloqueado})
            if bloqueados:
                raise ValidationError({
                    'detail': 'Hay movimientos en un periodo bloqueado.',
                    'errores': bloqueados,
                })
            ids = [mov_id for mov_id, _, _ in movimientos]
            ConMovimiento.objects.filter(id__in=ids).delete()
        return Response({'eliminados': len(ids)}, status=status.HTTP_200_OK)
