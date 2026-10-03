from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from general.models import GenDocumento
from general.servicios import documento_imprimir
from humano.formatos import FormatoProgramacion
from humano.models import HumProgramacion
from humano.serializers import (
    HumProgramacionExportarSerializer,
    HumProgramacionImportarSerializer,
    HumProgramacionSeleccionarSerializer,
    HumProgramacionSerializer,
)
from humano.servicios import (
    ProgramacionError,
    aprobar_programacion,
    cargar_contratos,
    desaprobar_programacion,
    desgenerar_programacion,
    eliminar_detalles,
    generar_programacion,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
    OpenApiParameter('estado_aprobado', bool, description='Filtrar por aprobado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


class CargarContratosRequestSerializer(serializers.Serializer):
    programacion_id = serializers.IntegerField()


class ProgramacionRequestSerializer(serializers.Serializer):
    programacion_id = serializers.IntegerField()


class EliminarDetallesRequestSerializer(serializers.Serializer):
    programacion_id = serializers.IntegerField()
    # Sin `ids` se eliminan todos; vacío no se acepta para que `[]` no borre todo.
    ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=False)


@extend_schema(tags=['Programación'])
class HumProgramacionViewSet(
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
    serializer_class = HumProgramacionSerializer
    serializer_class_exportar = HumProgramacionExportarSerializer
    serializer_class_importar = HumProgramacionImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = HumProgramacion.objects.select_related(
            *HumProgramacionSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)

        valor = self.request.query_params.get('estado_aprobado')
        if valor is not None:
            qs = qs.filter(estado_aprobado=valor.lower() == 'true')

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumProgramacionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumProgramacion.objects.order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumProgramacionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(request=CargarContratosRequestSerializer)
    @action(detail=False, methods=['post'], url_path='cargar-contrato')
    def cargar_contrato(self, request):
        """
        Crea un detalle por cada contrato del grupo que le aplique a la programación
        según su tipo de pago. Los que ya tienen detalle no se tocan.
        """
        serializer = CargarContratosRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            programacion = HumProgramacion.objects.get(pk=serializer.validated_data['programacion_id'])
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        try:
            creados = cargar_contratos(programacion)
        except ProgramacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        programacion.refresh_from_db(fields=['contratos'])
        return Response(
            {'creados': creados, 'contratos': programacion.contratos},
            status=status.HTTP_200_OK,
        )

    @extend_schema(request=EliminarDetallesRequestSerializer)
    @action(detail=False, methods=['post'], url_path='eliminar-detalle')
    def eliminar_detalle(self, request):
        """Elimina los detalles indicados en `ids` o, sin `ids`, todos los de la programación."""
        serializer = EliminarDetallesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        try:
            programacion = HumProgramacion.objects.get(pk=datos['programacion_id'])
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        try:
            eliminados = eliminar_detalles(programacion, datos.get('ids'))
        except ProgramacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        programacion.refresh_from_db(fields=['contratos'])
        return Response(
            {'eliminados': eliminados, 'contratos': programacion.contratos},
            status=status.HTTP_200_OK,
        )

    @extend_schema(request=ProgramacionRequestSerializer, responses=HumProgramacionSerializer)
    @action(detail=False, methods=['post'], url_path='generar')
    def generar(self, request):
        """Liquida la programación: un documento de nómina por detalle."""
        serializer = ProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            programacion = HumProgramacion.objects.get(pk=serializer.validated_data['programacion_id'])
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        try:
            programacion = generar_programacion(programacion)
        except ProgramacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumProgramacionSerializer(programacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=ProgramacionRequestSerializer, responses=HumProgramacionSerializer)
    @action(detail=False, methods=['post'], url_path='desgenerar')
    def desgenerar(self, request):
        """Borra los documentos de la programación generada y deja sus totales en cero."""
        serializer = ProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            programacion = HumProgramacion.objects.get(pk=serializer.validated_data['programacion_id'])
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        try:
            programacion = desgenerar_programacion(programacion)
        except ProgramacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumProgramacionSerializer(programacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=ProgramacionRequestSerializer, responses=HumProgramacionSerializer)
    @action(detail=False, methods=['post'], url_path='aprobar')
    def aprobar(self, request):
        """Aprueba los documentos, abona los créditos y mueve la fecha de último pago de los contratos."""
        serializer = ProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            programacion = HumProgramacion.objects.get(pk=serializer.validated_data['programacion_id'])
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        try:
            programacion = aprobar_programacion(programacion)
        except ProgramacionError as e:
            return Response({'detail': e.detail, 'errores': e.errores}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumProgramacionSerializer(programacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=ProgramacionRequestSerializer, responses=HumProgramacionSerializer)
    @action(detail=False, methods=['post'], url_path='desaprobar')
    def desaprobar(self, request):
        """Deshace la aprobación, si ningún documento tiene egreso ni está contabilizado."""
        serializer = ProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            programacion = HumProgramacion.objects.get(pk=serializer.validated_data['programacion_id'])
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        try:
            programacion = desaprobar_programacion(programacion)
        except ProgramacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(HumProgramacionSerializer(programacion).data, status=status.HTTP_200_OK)

    @extend_schema(request=ProgramacionRequestSerializer, responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'], url_path='imprimir')
    def imprimir(self, request):
        """Resumen de la programación en PDF: un empleado por fila con su cuenta, banco y totales."""
        serializer = ProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            programacion = HumProgramacion.objects.select_related('grupo', 'pago_tipo').get(
                pk=serializer.validated_data['programacion_id'],
            )
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        contenido, nombre = FormatoProgramacion(programacion).pdf()
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{nombre}"'
        return response

    @extend_schema(request=ProgramacionRequestSerializer, responses={(200, 'application/pdf'): OpenApiTypes.BINARY})
    @action(detail=False, methods=['post'], url_path='imprimir-nominas')
    def imprimir_nominas(self, request):
        """Los desprendibles de la programación en un solo PDF, uno por página y por empleado."""
        serializer = ProgramacionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            programacion = HumProgramacion.objects.get(pk=serializer.validated_data['programacion_id'])
        except HumProgramacion.DoesNotExist:
            raise NotFound('Programación no encontrada.')

        # Sin el tope de 50 de `documento/imprimir/`: una programación imprime
        # todos sus empleados de una vez.
        documentos = (
            GenDocumento.objects.filter(programacion_detalle__programacion=programacion)
            .select_related('documento_tipo', 'contacto__banco', 'contrato__cargo', 'contrato__grupo')
            .order_by('contacto__nombre_corto', 'id')
        )
        contenido, _ = documento_imprimir.imprimir(documentos)
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="nominas_programacion{programacion.id}.pdf"'
        return response
