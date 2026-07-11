import calendar
from collections import OrderedDict
from datetime import date

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento, GenDocumentoDetalle
from turno.models import TurProgramacionSimulacion
from turno.serializers import (
    TurProgramacionSimulacionExportarSerializer,
    TurProgramacionSimulacionImportarSerializer,
    TurProgramacionSimulacionSerializer,
)
from turno.servicios import simular as simular_servicio
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin


class SimularRequestSerializer(serializers.Serializer):
    documento_detalle_id = serializers.IntegerField()
    anio = serializers.IntegerField(min_value=2000, max_value=2100)
    mes = serializers.IntegerField(min_value=1, max_value=12)


_LIST_PARAMS = [
    OpenApiParameter('fecha', str, description='Filtrar por fecha (AAAA-MM-DD)'),
    OpenApiParameter('turno', int, description='Filtrar por turno'),
    OpenApiParameter('documento_detalle', int, description='Filtrar por documento detalle'),
]


@extend_schema(tags=['Turno'])
class TurProgramacionSimulacionViewSet(
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
    serializer_class = TurProgramacionSimulacionSerializer
    serializer_class_exportar = TurProgramacionSimulacionExportarSerializer
    serializer_class_importar = TurProgramacionSimulacionImportarSerializer

    def get_queryset(self):
        qs = TurProgramacionSimulacion.objects.select_related(
            *TurProgramacionSimulacionSerializer.select_related_lista
        ).order_by('fecha', 'id')

        fecha = self.request.query_params.get('fecha')
        if fecha:
            qs = qs.filter(fecha=fecha)

        turno = self.request.query_params.get('turno')
        if turno:
            qs = qs.filter(turno_id=turno)

        documento_detalle = self.request.query_params.get('documento_detalle')
        if documento_detalle:
            qs = qs.filter(documento_detalle_id=documento_detalle)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=SimularRequestSerializer)
    @action(detail=False, methods=['post'], url_path='simular')
    def simular(self, request):
        serializer = SimularRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        if not GenDocumentoDetalle.objects.filter(pk=datos['documento_detalle_id']).exists():
            raise NotFound('Documento detalle no encontrado.')

        creados = simular_servicio(
            datos['documento_detalle_id'], datos['anio'], datos['mes'],
        )
        return Response({'creados': creados}, status=status.HTTP_200_OK)

    @extend_schema(parameters=[
        OpenApiParameter('documento', int, required=True, description='Filtrar por documento'),
    ])
    @action(detail=False, methods=['get'], url_path='detalle')
    def detalle(self, request):
        # Grilla horizontal: una fila por (documento_detalle, contrato), columnas = fechas.
        # Se listan todos los documento_detalles del documento, aun sin simulación.
        valor = request.query_params.get('documento')
        if not valor:
            raise ValidationError({'documento': 'Este parámetro es obligatorio.'})
        try:
            documento_id = int(valor)
        except (TypeError, ValueError):
            raise ValidationError({'documento': 'Debe ser un entero.'})

        documento = (
            GenDocumento.objects.select_related('contacto').filter(pk=documento_id).first()
        )

        detalles = list(
            GenDocumentoDetalle.objects
            .filter(documento_id=documento_id)
            .select_related('puesto', 'modalidad')
            .order_by('id')
        )

        simulaciones = (
            TurProgramacionSimulacion.objects
            .filter(documento_detalle__documento_id=documento_id)
            .select_related('contrato__contacto', 'turno')
            .order_by('fecha', 'id')
        )

        # Columnas: el mes completo de documento.fecha, más cualquier fecha
        # simulada fuera de ese mes para no ocultar datos.
        fechas_mes = set()
        fecha_documento = documento.fecha if documento else None
        if fecha_documento:
            dias_mes = calendar.monthrange(fecha_documento.year, fecha_documento.month)[1]
            fechas_mes = {
                date(fecha_documento.year, fecha_documento.month, dia)
                for dia in range(1, dias_mes + 1)
            }
        fechas = sorted(fechas_mes | {s.fecha for s in simulaciones})
        fechas_iso = [f.isoformat() for f in fechas]

        # Agrupar por detalle -> contrato -> {fecha_iso: simulacion}.
        grupos = OrderedDict()
        for s in simulaciones:
            grupos.setdefault(s.documento_detalle_id, OrderedDict()) \
                  .setdefault(s.contrato_id, {})[s.fecha.isoformat()] = s

        def celda(s):
            if s is None:
                return None
            return {
                'simulacion_id': s.id,
                'turno_id': s.turno_id,
                'turno_codigo': s.turno.codigo if s.turno else None,
                'turno_nombre': s.turno.nombre if s.turno else None,
                'horas': s.horas,
                'horas_diurnas': s.horas_diurnas,
                'horas_nocturnas': s.horas_nocturnas,
                'festivo': s.festivo,
            }

        def construir_fila(detalle, contrato, posicion, por_fecha):
            return {
                'documento_detalle_id': detalle.id,
                'documento_detalle_afectado_id': detalle.documento_detalle_afectado_id,
                'puesto_id': detalle.puesto_id,
                'puesto_nombre': detalle.puesto.nombre if detalle.puesto else None,
                'modalidad_nombre': detalle.modalidad.nombre if detalle.modalidad else None,
                'fecha_desde': detalle.fecha_desde,
                'hora_desde': detalle.hora_desde,
                'hora_hasta': detalle.hora_hasta,
                'posicion': posicion,
                'contrato_id': contrato.id if contrato else None,
                'contrato_contacto_id': contrato.contacto_id if contrato else None,
                'contrato_contacto_nombre_corto': (
                    contrato.contacto.nombre_corto if contrato and contrato.contacto else None
                ),
                'contrato_contacto_numero_identificacion': (
                    contrato.contacto.numero_identificacion if contrato and contrato.contacto else None
                ),
                'horas': detalle.horas,
                'horas_diurnas': detalle.horas_diurnas,
                'horas_nocturnas': detalle.horas_nocturnas,
                'horas_programadas': detalle.horas_programadas,
                'horas_diurnas_programadas': detalle.horas_diurnas_programadas,
                'horas_nocturnas_programadas': detalle.horas_nocturnas_programadas,
                'dias': {iso: celda(por_fecha.get(iso)) for iso in fechas_iso},
            }

        filas = []
        for detalle in detalles:
            contratos = grupos.get(detalle.id)
            if not contratos:
                filas.append(construir_fila(detalle, None, None, {}))
                continue
            for por_fecha in contratos.values():
                fila_ref = next(iter(por_fecha.values()))
                filas.append(construir_fila(
                    detalle, fila_ref.contrato, fila_ref.posicion, por_fecha,
                ))

        documento_info = None
        if documento is not None:
            contacto = documento.contacto
            documento_info = {
                'id': documento.id,
                'numero': documento.numero,
                'fecha': documento.fecha,
                'horas': documento.horas,
                'horas_diurnas': documento.horas_diurnas,
                'horas_nocturnas': documento.horas_nocturnas,
                'horas_programadas': documento.horas_programadas,
                'horas_diurnas_programadas': documento.horas_diurnas_programadas,
                'horas_nocturnas_programadas': documento.horas_nocturnas_programadas,
                'contacto_nombre_corto': contacto.nombre_corto if contacto else None,
                'contacto_numero_identificacion': (
                    contacto.numero_identificacion if contacto else None
                ),
            }

        return Response({
            'documento': documento_info,
            'fechas': fechas_iso,
            'filas': filas,
        })
