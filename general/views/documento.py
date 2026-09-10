from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento
from general.serializers import (
    GenDocumentoCrearSerializer,
    GenDocumentoExportarSerializer,
    GenDocumentoGenerarRecurrenteSerializer,
    GenDocumentoImportarSerializer,
    GenDocumentoSerializer,
)
from general.servicios import contabilizar as contabilizar_servicio
from general.servicios import documento as documento_servicio
from general.servicios import documento_imprimir
from utilidades.filtros import aplicar_filtros
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.mixins.filtros import BusquedaRequest
from seguridad.permissions import TienePermisoModelo


class DocumentoAccionRequestSerializer(serializers.Serializer):
    """Un documento sobre el que actuar. El id va crudo al servicio, que es quien
    resuelve la fila con `select_for_update` y responde 404 si no existe."""

    id = serializers.IntegerField(min_value=1, help_text='Id del documento.')


class DocumentoIdsRequestSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text='Ids de los documentos a procesar.',
    )


@extend_schema(tags=['Documento'])
class GenDocumentoViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenDocumentoSerializer
    serializer_class_exportar = GenDocumentoExportarSerializer
    serializer_class_importar = GenDocumentoImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_serializer_class(self):
        if self.action == 'create':
            return GenDocumentoCrearSerializer
        return GenDocumentoSerializer

    def get_queryset(self):
        select = GenDocumentoSerializer.select_related_lista
        return GenDocumento.objects.select_related(*select)

    def update(self, request, *args, **kwargs):
        instancia = self.get_object()
        if not instancia.es_mutable():
            raise ValidationError('El documento no es modificable.')
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            try:
                documento = GenDocumento.objects.select_for_update().get(pk=kwargs['pk'])
            except GenDocumento.DoesNotExist:
                raise NotFound('Documento no encontrado.')
            if not documento.es_mutable():
                raise ValidationError('El documento no es modificable.')
            documento.documentos_detalles_documento_rel.all().delete()
            documento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _queryset_imprimir(self, request):
        filtros = request.data.get('filtros') or []
        if not filtros:
            raise ValidationError('Debe enviar al menos un filtro para imprimir.')
        campos_filtrables = self._config_lista('campos_filtrables', set())
        qs = self.get_queryset().select_related(
            # `cuenta_banco__cuenta` y el documento afectado los lee el formato
            # del egreso; sin esto serían una consulta por línea impresa.
            'documento_tipo', 'contacto', 'cuenta_banco__cuenta',
        ).prefetch_related(
            'documentos_detalles_documento_rel__item',
            'documentos_detalles_documento_rel__cuenta',
            'documentos_detalles_documento_rel__contacto',
            'documentos_detalles_documento_rel__documento_afectado',
        )
        qs = aplicar_filtros(qs, filtros, campos_filtrables)
        if qs.count() > 50:
            raise ValidationError(
                'No se pueden imprimir más de 50 documentos a la vez. Afine los filtros.'
            )
        return qs

    @extend_schema(
        summary='Obsoleto: use documento/generar-recurrente/',
        description=(
            'Reemplazado por `documento/generar-recurrente/`, que recibe los ids y '
            'resuelve solo qué hacer con cada uno según su tipo. La generación de '
            'contratos de servicio (tipo 34) vive ahora ahí.'
        ),
        request=None,
        responses={400: OpenApiTypes.OBJECT},
        deprecated=True,
    )
    @action(detail=False, methods=['post'])
    def generar(self, request):
        raise ValidationError(
            {'detail': 'Endpoint retirado. Use documento/generar-recurrente/.'}
        )

    @extend_schema(request=DocumentoAccionRequestSerializer, responses=GenDocumentoSerializer)
    @extend_schema(
        summary='Generar documentos desde plantillas recurrentes',
        description=(
            'Genera un documento nuevo del `documento_tipo_destino` indicado desde cada '
            'plantilla recurrente, para el periodo `anio`/`mes`.\n\n'
            'Las plantillas se eligen con `documento_tipo_origen` (todas las de ese '
            'tipo), con `documento_ids`, o con los dos a la vez, donde los ids acotan '
            'la selección del tipo. Hay que mandar al menos uno de los dos.\n\n'
            '- **16 y 32** (factura de venta y de compra recurrente): se copian enteras '
            'con sus detalles e impuestos. Se emiten **con fecha de hoy** y vencen a los '
            'días del plazo de pago del origen; la plantilla queda intacta. No usan '
            '`anio`/`mes`.\n'
            '- **34** (contrato de servicio): los detalles se recortan a la ventana del '
            'periodo y se les recalculan horas, diurnas, nocturnas y días contra el '
            'calendario real con sus festivos; el contrato origen avanza al mes siguiente.\n\n'
            'El documento nuevo nace sin numerar y sin aprobar. Es una sola transacción: '
            'si un documento falla, no se crea ninguno.\n\n'
            'Responde `{"generados": <n>}` con la cantidad creada.'
        ),
        request=GenDocumentoGenerarRecurrenteSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'], url_path='generar-recurrente')
    def generar_recurrente(self, request):
        serializer = GenDocumentoGenerarRecurrenteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        tipo_origen = datos.get('documento_tipo_origen')
        generados = documento_servicio.generar_recurrente(
            documento_tipo_destino_id=datos['documento_tipo_destino'].pk,
            anio=datos['anio'],
            mes=datos['mes'],
            documento_ids=datos.get('documento_ids'),
            documento_tipo_origen_id=tipo_origen.pk if tipo_origen else None,
        )
        return Response({'generados': len(generados)}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def aprobar(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = documento_servicio.aprobar(serializer.validated_data['id'])
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(request=DocumentoAccionRequestSerializer, responses=GenDocumentoSerializer)
    @action(detail=False, methods=['post'])
    def desaprobar(self, request):
        serializer = DocumentoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documento = documento_servicio.desaprobar(serializer.validated_data['id'])
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Contabilizar documentos',
        description=(
            'Genera los movimientos contables de cada documento aprobado y lo marca '
            'como contabilizado. El lote va en una sola transacción: si un documento '
            'falla, no queda ninguno contabilizado.'
        ),
        request=DocumentoIdsRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'])
    def contabilizar(self, request):
        serializer = DocumentoIdsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cantidad = contabilizar_servicio.contabilizar(serializer.validated_data['ids'])
        return Response({'contabilizados': cantidad}, status=status.HTTP_200_OK)

    @extend_schema(
        summary='Descontabilizar documentos',
        description=(
            'Borra los movimientos contables de cada documento y le quita el '
            'contabilizado. Mismo criterio de transacción que `contabilizar`.'
        ),
        request=DocumentoIdsRequestSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'])
    def descontabilizar(self, request):
        serializer = DocumentoIdsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cantidad = contabilizar_servicio.descontabilizar(serializer.validated_data['ids'])
        return Response({'descontabilizados': cantidad}, status=status.HTTP_200_OK)

    @extend_schema(request=BusquedaRequest, responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'])
    def imprimir(self, request):
        contenido, nombre = documento_imprimir.imprimir(self._queryset_imprimir(request))
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{nombre}"'
        return response

    @extend_schema(request=BusquedaRequest, responses={(200, 'application/zip'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'], url_path='imprimir-zip')
    def imprimir_zip(self, request):
        contenido, nombre = documento_imprimir.imprimir_zip(self._queryset_imprimir(request))
        response = HttpResponse(contenido, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return response

    @extend_schema(
        parameters=[
            OpenApiParameter('fecha_desde', OpenApiTypes.DATE, description='Fecha desde (AAAA-MM-DD)'),
            OpenApiParameter('fecha_hasta', OpenApiTypes.DATE, description='Fecha hasta (AAAA-MM-DD)'),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['get'], url_path='analitica-horas')
    def analitica_horas(self, request):
        # Recuerda: en el modelo `horas` = planeado y `horas_programadas` = ejecutado.
        # Validación de parámetros inline.
        fecha_desde = None
        fecha_hasta = None
        valor = request.query_params.get('fecha_desde')
        if valor:
            try:
                fecha_desde = datetime.strptime(valor.strip(), '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError({'fecha_desde': 'Formato inválido, use AAAA-MM-DD.'})
        valor = request.query_params.get('fecha_hasta')
        if valor:
            try:
                fecha_hasta = datetime.strptime(valor.strip(), '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError({'fecha_hasta': 'Formato inválido, use AAAA-MM-DD.'})
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            raise ValidationError({'fecha_desde': 'No puede ser mayor que fecha_hasta.'})

        # Solo documentos tipo 35 y válidos (aprobados y no anulados).
        qs = GenDocumento.objects.filter(
            documento_tipo_id=35, estado_aprobado=True, estado_anulado=False
        )
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        # Una sola query: suma por mes en la BD.
        filas = (
            qs.annotate(periodo=TruncMonth('fecha'))
            .values('periodo')
            .annotate(
                planeadas=Sum('horas'),
                ejecutadas=Sum('horas_programadas'),
                planeadas_diurnas=Sum('horas_diurnas'),
                ejecutadas_diurnas=Sum('horas_diurnas_programadas'),
                planeadas_nocturnas=Sum('horas_nocturnas'),
                ejecutadas_nocturnas=Sum('horas_nocturnas_programadas'),
            )
            .order_by('periodo')
        )

        cero = Decimal('0')

        def cumplimiento(ejecutadas, planeadas):
            if not planeadas:
                return None
            return round(float(ejecutadas / planeadas * 100), 1)

        serie = []
        tot_plan = tot_ejec = cero
        tot_plan_diu = tot_ejec_diu = cero
        tot_plan_noc = tot_ejec_noc = cero
        for fila in filas:
            planeadas = fila['planeadas'] or cero
            ejecutadas = fila['ejecutadas'] or cero
            tot_plan += planeadas
            tot_ejec += ejecutadas
            tot_plan_diu += fila['planeadas_diurnas'] or cero
            tot_ejec_diu += fila['ejecutadas_diurnas'] or cero
            tot_plan_noc += fila['planeadas_nocturnas'] or cero
            tot_ejec_noc += fila['ejecutadas_nocturnas'] or cero
            serie.append({
                'periodo': fila['periodo'].strftime('%Y-%m'),
                'planeadas': planeadas,
                'ejecutadas': ejecutadas,
                'cumplimiento': cumplimiento(ejecutadas, planeadas),
            })

        resumen = {
            'horas_planeadas': tot_plan,
            'horas_ejecutadas': tot_ejec,
            'cumplimiento': cumplimiento(tot_ejec, tot_plan),
            'desviacion': tot_ejec - tot_plan,
            'diurnas': {'planeadas': tot_plan_diu, 'ejecutadas': tot_ejec_diu},
            'nocturnas': {'planeadas': tot_plan_noc, 'ejecutadas': tot_ejec_noc},
        }

        return Response({
            'resumen': resumen,
            'serie': serie,
            'agrupado_por': 'mes',
        })
