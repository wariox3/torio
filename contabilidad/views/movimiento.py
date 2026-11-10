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
from utilidades.filtros import aplicar_filtros
from utilidades.mixins.filtros import BusquedaRequest
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

    def _eliminar_saldos_iniciales(self, qs):
        """Borra los movimientos de `qs`, todo o nada, si ninguno está en un periodo bloqueado.

        Solo se borran saldos iniciales: los demás movimientos los crea la
        contabilización de un documento y se quitan descontabilizándolo.
        """
        with transaction.atomic():
            movimientos = list(qs.select_for_update().values_list('id', 'periodo__estado_bloqueado'))
            bloqueados = [mov_id for mov_id, bloqueado in movimientos if bloqueado]
            if bloqueados:
                raise ValidationError({
                    'detail': 'Hay movimientos en un periodo bloqueado.',
                    'errores': bloqueados,
                })
            ids = [mov_id for mov_id, _ in movimientos]
            ConMovimiento.objects.filter(id__in=ids).delete()
        return Response({'eliminados': len(ids)}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Eliminar seleccionados',
        description='Elimina los movimientos indicados. Todos deben ser de saldo inicial; si alguno no lo es, no se elimina ninguno.',
        request=inline_serializer(
            name='MovimientoEliminarRequest',
            fields={'ids': serializers.ListField(child=serializers.IntegerField(), allow_empty=False)},
        ),
        responses=_ELIMINADOS_RESPONSE,
    )
    @action(detail=False, methods=['post'], url_path='eliminar')
    def eliminar(self, request):
        ids = request.data.get('ids')
        if not isinstance(ids, list) or not ids:
            raise ValidationError({'detail': 'ids debe ser una lista no vacía.'})
        try:
            ids = {int(valor) for valor in ids}
        except (TypeError, ValueError):
            raise ValidationError({'detail': 'ids debe contener solo enteros.'})

        encontrados = dict(
            ConMovimiento.objects.filter(id__in=ids).values_list('id', 'saldo_inicial')
        )
        inexistentes = sorted(ids - encontrados.keys())
        if inexistentes:
            raise ValidationError({'detail': 'Hay movimientos que no existen.', 'errores': inexistentes})
        no_saldo = sorted(mov_id for mov_id, saldo in encontrados.items() if not saldo)
        if no_saldo:
            raise ValidationError({
                'detail': 'Solo se pueden eliminar movimientos de saldo inicial.',
                'errores': no_saldo,
            })

        return self._eliminar_saldos_iniciales(
            ConMovimiento.objects.filter(id__in=ids, saldo_inicial=True)
        )

    @extend_schema(
        summary='Eliminar según filtros',
        description=(
            'Elimina los movimientos de saldo inicial que cumplan los `filtros` (los mismos de `lista`). '
            'Los que no son de saldo inicial se ignoran. Exige al menos un filtro.'
        ),
        request=BusquedaRequest,
        responses=_ELIMINADOS_RESPONSE,
    )
    @action(detail=False, methods=['post'], url_path='eliminar-masivo')
    def eliminar_masivo(self, request):
        filtros = request.data.get('filtros')
        if not filtros:
            raise ValidationError({'detail': 'Debe enviar al menos un filtro.'})

        qs = aplicar_filtros(
            ConMovimiento.objects.filter(saldo_inicial=True),
            filtros,
            ConMovimientoSerializer.campos_filtrables,
        )
        return self._eliminar_saldos_iniciales(qs)
