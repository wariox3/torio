import calendar
from collections import OrderedDict
from datetime import date

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento, GenDocumentoDetalle
from humano.models import HumContrato
from turno.models import TurProgramacion
from turno.serializers import (
    TurProgramacionExportarSerializer,
    TurProgramacionImportarSerializer,
    TurProgramacionSerializer,
)
from turno.servicios import (
    ProgramacionError,
    actualizar_programacion,
    crear_programacion,
    eliminar_programaciones,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin


class ItemCrearProgramacionSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    turno_codigo = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class CrearProgramacionRequestSerializer(serializers.Serializer):
    contrato_id = serializers.IntegerField()
    documento_detalle_id = serializers.IntegerField()
    items = ItemCrearProgramacionSerializer(many=True, allow_empty=False)


class EliminarProgramacionRequestSerializer(serializers.Serializer):
    contrato_id = serializers.IntegerField()
    documento_detalle_id = serializers.IntegerField()


class ActualizarProgramacionMasivoRequestSerializer(serializers.Serializer):
    programaciones = CrearProgramacionRequestSerializer(many=True, allow_empty=False)


class EliminarProgramacionMasivoRequestSerializer(serializers.Serializer):
    programaciones = EliminarProgramacionRequestSerializer(many=True, allow_empty=False)


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

        if TurProgramacion.objects.filter(
            contrato=contrato, documento_detalle=documento_detalle
        ).exists():
            raise ValidationError(
                {'detail': 'Ya existe programación para este contrato y puesto; use actualizar.'}
            )

        try:
            creados = crear_programacion(contrato, documento_detalle, datos['items'])
        except ProgramacionError as e:
            return Response(
                {'detail': e.detail, 'errores': e.errores},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'creados': creados}, status=status.HTTP_201_CREATED)

    @extend_schema(request=CrearProgramacionRequestSerializer)
    @action(detail=False, methods=['post'], url_path='actualizar-programacion')
    def actualizar_programacion(self, request):
        """Sincroniza las programaciones de un (contrato, documento_detalle) con los items enviados."""
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
            resultado = actualizar_programacion(contrato, documento_detalle, datos['items'])
        except ProgramacionError as e:
            return Response(
                {'detail': e.detail, 'errores': e.errores},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(resultado, status=status.HTTP_200_OK)

    @extend_schema(request=ActualizarProgramacionMasivoRequestSerializer)
    @action(detail=False, methods=['post'], url_path='actualizar-programacion-masivo')
    def actualizar_programacion_masivo(self, request):
        """
        Reconcilia varias programaciones (contrato, documento_detalle) en un lote.

        Es todo o nada: si algún elemento tiene errores, se revierte todo el lote
        y se devuelven los resultados/errores por índice.
        """
        serializer = ActualizarProgramacionMasivoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lote = serializer.validated_data['programaciones']

        resultados = []
        hay_errores = False
        with transaction.atomic():
            for indice, elem in enumerate(lote):
                contrato = HumContrato.objects.filter(pk=elem['contrato_id']).first()
                if contrato is None:
                    resultados.append({'indice': indice, 'detail': 'Contrato no encontrado.'})
                    hay_errores = True
                    continue
                if not contrato.habilitado_turno:
                    resultados.append({'indice': indice, 'detail': 'El contrato no está habilitado para turnos.'})
                    hay_errores = True
                    continue
                documento_detalle = GenDocumentoDetalle.objects.filter(pk=elem['documento_detalle_id']).first()
                if documento_detalle is None:
                    resultados.append({'indice': indice, 'detail': 'Documento detalle no encontrado.'})
                    hay_errores = True
                    continue
                try:
                    resultado = actualizar_programacion(contrato, documento_detalle, elem['items'])
                except ProgramacionError as e:
                    resultados.append({'indice': indice, 'errores': e.errores})
                    hay_errores = True
                    continue
                resultados.append({'indice': indice, **resultado})

            if hay_errores:
                transaction.set_rollback(True)

        if hay_errores:
            return Response(
                {'detail': 'Hay elementos con errores.', 'resultados': resultados},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'resultados': resultados}, status=status.HTTP_200_OK)

    @extend_schema(request=EliminarProgramacionRequestSerializer)
    @action(detail=False, methods=['post'], url_path='eliminar-programacion')
    def eliminar_programacion(self, request):
        """Elimina las programaciones de un (contrato, documento_detalle)."""
        serializer = EliminarProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        with transaction.atomic():
            eliminados = eliminar_programaciones(
                datos['contrato_id'], datos['documento_detalle_id']
            )
        return Response({'eliminados': eliminados}, status=status.HTTP_200_OK)

    @extend_schema(request=EliminarProgramacionMasivoRequestSerializer)
    @action(detail=False, methods=['post'], url_path='eliminar-programacion-masivo')
    def eliminar_programacion_masivo(self, request):
        """Elimina las programaciones de varios (contrato, documento_detalle) en un lote (todo o nada)."""
        serializer = EliminarProgramacionMasivoRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lote = serializer.validated_data['programaciones']

        with transaction.atomic():
            eliminados = sum(
                eliminar_programaciones(elem['contrato_id'], elem['documento_detalle_id'])
                for elem in lote
            )
        return Response({'eliminados': eliminados}, status=status.HTTP_200_OK)

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

        documento = (
            GenDocumento.objects.select_related('contacto').filter(pk=documento_id).first()
        )

        detalles = list(
            GenDocumentoDetalle.objects
            .filter(documento_id=documento_id)
            .select_related('puesto', 'modalidad')
            .order_by('id')
        )

        programaciones = (
            TurProgramacion.objects
            .filter(documento_detalle__documento_id=documento_id)
            .select_related('contrato__contacto', 'turno')
            .order_by('fecha', 'id')
        )

        # Columnas: el mes completo de documento.fecha, más cualquier fecha
        # programada fuera de ese mes para no ocultar datos.
        fechas_mes = set()
        fecha_documento = documento.fecha if documento else None
        if fecha_documento:
            dias_mes = calendar.monthrange(fecha_documento.year, fecha_documento.month)[1]
            fechas_mes = {
                date(fecha_documento.year, fecha_documento.month, dia)
                for dia in range(1, dias_mes + 1)
            }
        fechas = sorted(fechas_mes | {p.fecha for p in programaciones})
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
                'documento_detalle_afectado_id': detalle.documento_detalle_afectado_id,
                'puesto_id': detalle.puesto_id,
                'puesto_nombre': detalle.puesto.nombre if detalle.puesto else None,
                'modalidad_nombre': detalle.modalidad.nombre if detalle.modalidad else None,
                'fecha_desde': detalle.fecha_desde,
                'hora_desde': detalle.hora_desde,
                'hora_hasta': detalle.hora_hasta,
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
                filas.append(construir_fila(detalle, None, {}))
                continue
            for por_fecha in contratos.values():
                contrato = next(iter(por_fecha.values())).contrato
                filas.append(construir_fila(detalle, contrato, por_fecha))

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
