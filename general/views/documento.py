from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento
from general.serializers import (
    GenDocumentoCrearSerializer,
    GenDocumentoExportarSerializer,
    GenDocumentoGenerarSerializer,
    GenDocumentoImportarSerializer,
    GenDocumentoSerializer,
)
from general.servicios import documento as documento_servicio
from general.servicios import documento_imprimir
from utilidades.filtros import aplicar_filtros
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.mixins.filtros import BusquedaRequest


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

    @extend_schema(request=GenDocumentoGenerarSerializer, responses=GenDocumentoSerializer(many=True))
    @action(detail=False, methods=['post'])
    def generar(self, request):
        serializer = GenDocumentoGenerarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        generados = documento_servicio.generar(
            documento_tipo_origen=datos['documento_tipo_id'],
            documento_tipo_destino_id=datos['documento_tipo_id_destino'].pk,
            anio=datos['anio'],
            mes=datos['mes'],
            documento_ids=datos.get('documento_ids'),
        )
        salida = GenDocumentoSerializer(generados, many=True)
        return Response(
            {'generados': len(generados), 'documentos': salida.data},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['post'])
    def aprobar(self, request):
        documento_id = request.data.get('id')
        if not documento_id:
            raise ValidationError({'id': 'Este campo es requerido.'})
        documento = documento_servicio.aprobar(documento_id)
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def desaprobar(self, request):
        documento_id = request.data.get('id')
        if not documento_id:
            raise ValidationError({'id': 'Este campo es requerido.'})
        documento = documento_servicio.desaprobar(documento_id)
        salida = GenDocumentoSerializer(documento)
        return Response(salida.data, status=status.HTTP_200_OK)

    def _queryset_imprimir(self, request):
        filtros = request.data.get('filtros') or []
        if not filtros:
            raise ValidationError('Debe enviar al menos un filtro para imprimir.')
        campos_filtrables = self._config_lista('campos_filtrables', set())
        qs = self.get_queryset().select_related('documento_tipo', 'contacto').prefetch_related(
            'documentos_detalles_documento_rel__item'
        )
        qs = aplicar_filtros(qs, filtros, campos_filtrables)
        if qs.count() > 50:
            raise ValidationError(
                'No se pueden imprimir más de 50 documentos a la vez. Afine los filtros.'
            )
        return qs

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
