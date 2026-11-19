from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from general.models import GenDocumentoDetalle
from humano.models import HumCredito
from humano.serializers import (
    HumCreditoExportarSerializer,
    HumCreditoImportarSerializer,
    HumCreditoSeleccionarSerializer,
    HumCreditoSerializer,
)
from humano.servicios import credito as credito_servicio
from seguridad.permissions import EsMiembroDelTenant, SuscripcionVigente, TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
    OpenApiParameter('inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]


@extend_schema(tags=['Crédito'])
class HumCreditoViewSet(
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
    serializer_class = HumCreditoSerializer
    serializer_class_exportar = HumCreditoExportarSerializer
    serializer_class_importar = HumCreditoImportarSerializer
    permission_classes = [TienePermisoModelo]

    def perform_destroy(self, instance):
        # Las líneas de nómina que descontaron cuotas apuntan al crédito con
        # PROTECT; se revisa antes para decir dónde está y qué hacer.
        linea = (
            GenDocumentoDetalle.objects.filter(credito=instance)
            .select_related('documento__documento_tipo').order_by('id').first()
        )
        if linea is not None:
            documento = linea.documento
            nombre = ' '.join(
                str(parte) for parte in (documento.documento_tipo.nombre, documento.numero) if parte is not None
            )
            raise ValidationError({'detail': (
                f'El crédito tiene cuotas descontadas en el documento {documento.pk} ({nombre}); '
                f'inactívelo en lugar de eliminarlo.'
            )})
        # Un crédito migrado puede traer abonos sin líneas de nómina que los respalden.
        if instance.abono > 0:
            raise ValidationError({'detail': 'El crédito tiene abonos; inactívelo en lugar de eliminarlo.'})
        instance.delete()

    def get_queryset(self):
        qs = HumCredito.objects.select_related(
            *HumCreditoSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)

        valor = self.request.query_params.get('inactivo')
        if valor is not None:
            qs = qs.filter(inactivo=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumCreditoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumCredito.objects.select_related('contrato__contacto').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumCreditoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Validar los saldos de los créditos',
        description=(
            'Recalcula desde su origen `abono`, `cuota_actual` y `saldo` de todos los '
            'créditos y corrige los que no coinciden con lo guardado; los que cuadran '
            'no se tocan. El abono es la suma de lo descontado por el crédito en '
            'documentos de nómina aprobados y sin anular, `cuota_actual` cuántas veces '
            'se descontó, y el saldo es `total - abono`. Lo puede correr cualquier '
            'miembro del contenedor.\n\n'
            'Responde `{"ejecutado": true, "corregidos": <n>}` cuando el proceso termina.'
        ),
        request=None,
        responses=OpenApiTypes.OBJECT,
    )
    @action(
        detail=False, methods=['post'], url_path='validar',
        permission_classes=[EsMiembroDelTenant, SuscripcionVigente],
    )
    def validar(self, request):
        corregidos = credito_servicio.validar()
        return Response({'ejecutado': True, 'corregidos': corregidos}, status=status.HTTP_200_OK)
