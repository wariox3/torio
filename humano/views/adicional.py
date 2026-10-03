from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from humano.models import HumAdicional, HumProgramacion
from humano.models.programacion_detalle import MENSAJE_PROGRAMACION_CERRADA
from humano.serializers import (
    HumAdicionalExportarSerializer,
    HumAdicionalImportarSerializer,
    HumAdicionalSeleccionarSerializer,
    HumAdicionalSerializer,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion
from utilidades.throttles import ImportarUsuarioTenantThrottle

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
    OpenApiParameter('inactivo', bool, description='Filtrar por inactivo'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]

_ImportarAdicionalRequest = inline_serializer(
    name='ImportarAdicionalRequest',
    fields={
        'archivo': serializers.FileField(help_text='Archivo .xlsx'),
        'permanente': serializers.BooleanField(help_text='true: adicionales libres; false: de una programación'),
        'programacion_id': serializers.IntegerField(
            required=False, help_text='Obligatorio si `permanente` es false; prohibido si es true.',
        ),
    },
)


class ImportarAdicionalRequestSerializer(serializers.Serializer):
    permanente = serializers.BooleanField()
    programacion_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        # En multipart DRF toma un booleano ausente como False, y eso volvería
        # "de programación" un archivo al que el front no le dijo el modo.
        if 'permanente' not in self.initial_data:
            raise serializers.ValidationError({'permanente': 'Este campo es requerido.'})
        if attrs['permanente'] and 'programacion_id' in attrs:
            raise serializers.ValidationError(
                {'programacion_id': 'Un adicional permanente no es de una programación.'},
            )
        if not attrs['permanente'] and 'programacion_id' not in attrs:
            raise serializers.ValidationError(
                {'programacion_id': 'Un adicional no permanente debe ser de una programación.'},
            )
        return attrs


@extend_schema(tags=['Adicional'])
class HumAdicionalViewSet(
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
    serializer_class = HumAdicionalSerializer
    serializer_class_exportar = HumAdicionalExportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = HumAdicional.objects.select_related(
            *HumAdicionalSerializer.select_related_lista
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

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumAdicionalSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumAdicional.objects.select_related('contrato__contacto', 'concepto').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumAdicionalSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    # ---- importación ----
    #
    # El modo (libres o de una programación) lo manda el front junto al archivo y
    # vale para todas las filas; la plantilla es la misma en los dos modos.

    def get_serializer_importar(self):
        if self.action == 'importar':
            return HumAdicionalImportarSerializer(
                permanente=self.permanente_importar, programacion=self.programacion_importar,
            )
        return HumAdicionalImportarSerializer(permanente=True)

    @extend_schema(
        summary='Importar adicionales desde Excel',
        description=(
            'Con `permanente=true` crea adicionales libres, que se pagan en todas las '
            'nóminas hasta inactivarlos. Con `permanente=false` los crea en la '
            'programación `programacion_id`, que debe estar sin generar. El modo vale '
            'para todo el archivo. Procesamiento todo-o-nada: si alguna fila falla, no '
            'se guarda nada.'
        ),
        request={'multipart/form-data': _ImportarAdicionalRequest},
    )
    @action(
        detail=False, methods=['post'],
        parser_classes=[MultiPartParser],
        throttle_classes=[ImportarUsuarioTenantThrottle],
    )
    def importar(self, request):
        serializer = ImportarAdicionalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        programacion = None
        if not datos['permanente']:
            try:
                programacion = HumProgramacion.objects.get(pk=datos['programacion_id'])
            except HumProgramacion.DoesNotExist:
                raise NotFound('Programación no encontrada.')
            if programacion.estado_generado or programacion.estado_aprobado:
                return Response({'detail': MENSAJE_PROGRAMACION_CERRADA}, status=status.HTTP_400_BAD_REQUEST)

        self.permanente_importar = datos['permanente']
        self.programacion_importar = programacion
        return super().importar(request)
