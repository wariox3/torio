from collections import OrderedDict

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumentoDetalle
from humano.models import HumContrato
from turno.models import TurProgramacion
from turno.serializers import (
    TurProgramacionExportarSerializer,
    TurProgramacionImportarSerializer,
    TurProgramacionSerializer,
)
from turno.servicios import ProgramacionExistenteError, crear_programacion
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin


class ItemCrearProgramacionSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    turno_codigo = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class CrearProgramacionRequestSerializer(serializers.Serializer):
    contrato_id = serializers.IntegerField()
    documento_detalle_id = serializers.IntegerField()
    items = ItemCrearProgramacionSerializer(many=True, allow_empty=False)


_LIST_PARAMS = [
    OpenApiParameter('contrato', int, description='Filtrar por contrato'),
    OpenApiParameter('fecha', str, description='Filtrar por fecha (AAAA-MM-DD)'),
]


@extend_schema(tags=['Turno'])
class TurProgramacionViewSet(
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
    serializer_class = TurProgramacionSerializer
    serializer_class_exportar = TurProgramacionExportarSerializer
    serializer_class_importar = TurProgramacionImportarSerializer

    def get_queryset(self):
        qs = TurProgramacion.objects.select_related(
            *TurProgramacionSerializer.select_related_lista
        ).order_by('fecha', 'id')

        contrato = self.request.query_params.get('contrato')
        if contrato:
            qs = qs.filter(contrato_id=contrato)

        fecha = self.request.query_params.get('fecha')
        if fecha:
            qs = qs.filter(fecha=fecha)

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=CrearProgramacionRequestSerializer)
    @action(detail=False, methods=['post'], url_path='crear-programacion')
    def crear_programacion(self, request):
        serializer = CrearProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        try:
            contrato = HumContrato.objects.get(pk=datos['contrato_id'])
        except HumContrato.DoesNotExist:
            raise NotFound('Contrato no encontrado.')
        if not contrato.habilitado_turno:
            raise ValidationError({'detail': 'El contrato no está habilitado para turnos.'})

        try:
            documento_detalle = GenDocumentoDetalle.objects.get(pk=datos['documento_detalle_id'])
        except GenDocumentoDetalle.DoesNotExist:
            raise NotFound('Documento detalle no encontrado.')

        try:
            creados = crear_programacion(contrato, documento_detalle, datos['items'])
        except ProgramacionExistenteError as e:
            return Response(
                {
                    'detail': str(e),
                    'existentes': [
                        {
                            'programacion_id': p.id,
                            'fecha': p.fecha.isoformat(),
                            'turno_id': p.turno_id,
                            'turno_codigo': p.turno.codigo if p.turno else None,
                            'turno_nombre': p.turno.nombre if p.turno else None,
                            'horas': p.horas,
                            'horas_diurnas': p.horas_diurnas,
                            'horas_nocturnas': p.horas_nocturnas,
                            'festivo': p.festivo,
                        }
                        for p in e.programaciones
                    ],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e:
            raise ValidationError({'detail': str(e)})

        return Response({'creados': creados}, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[
        OpenApiParameter('documento', int, required=True, description='Filtrar por documento'),
    ])
    @action(detail=False, methods=['get'], url_path='detalle')
    def detalle(self, request):
        # Grilla horizontal: una fila por (documento_detalle, contrato), columnas = fechas.
        # Se listan todos los documento_detalles del documento, aun sin programación.
        valor = request.query_params.get('documento')
        if not valor:
            raise ValidationError({'documento': 'Este parámetro es obligatorio.'})
        try:
            documento_id = int(valor)
        except (TypeError, ValueError):
            raise ValidationError({'documento': 'Debe ser un entero.'})

        detalles = list(
            GenDocumentoDetalle.objects
            .filter(documento_id=documento_id)
            .select_related('puesto')
            .order_by('id')
        )

        programaciones = (
            TurProgramacion.objects
            .filter(documento_detalle__documento_id=documento_id)
            .select_related('contrato__contacto', 'turno')
            .order_by('fecha', 'id')
        )

        # Columnas: unión ordenada de fechas presentes.
        fechas = sorted({p.fecha for p in programaciones})
        fechas_iso = [f.isoformat() for f in fechas]

        # Agrupar por detalle -> contrato -> {fecha_iso: programacion}.
        grupos = OrderedDict()
        for p in programaciones:
            grupos.setdefault(p.documento_detalle_id, OrderedDict()) \
                  .setdefault(p.contrato_id, {})[p.fecha.isoformat()] = p

        def celda(p):
            if p is None:
                return None
            return {
                'programacion_id': p.id,
                'turno_id': p.turno_id,
                'turno_codigo': p.turno.codigo if p.turno else None,
                'turno_nombre': p.turno.nombre if p.turno else None,
                'horas': p.horas,
                'horas_diurnas': p.horas_diurnas,
                'horas_nocturnas': p.horas_nocturnas,
                'festivo': p.festivo,
            }

        def construir_fila(detalle, contrato, por_fecha):
            return {
                'documento_detalle_id': detalle.id,
                'puesto_id': detalle.puesto_id,
                'puesto_nombre': detalle.puesto.nombre if detalle.puesto else None,
                'contrato_id': contrato.id if contrato else None,
                'contrato_nombre': (
                    contrato.contacto.nombre_corto if contrato and contrato.contacto else None
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
                filas.append(construir_fila(detalle, None, {}))
                continue
            for por_fecha in contratos.values():
                contrato = next(iter(por_fecha.values())).contrato
                filas.append(construir_fila(detalle, contrato, por_fecha))

        return Response({
            'documento': documento_id,
            'fechas': fechas_iso,
            'filas': filas,
        })
