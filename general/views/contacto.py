from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenContacto, GenIdentificacion
from general.serializers import (
    GenContactoExportarSerializer,
    GenContactoImportarSerializer,
    GenContactoSeleccionarSerializer,
    GenContactoSerializer,
)
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin, ImportarExcelMixin
from utilidades.paginacion import SeleccionarPaginacion
from utilidades.wolframio import Wolframio

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre corto o número de identificación'),
]

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre corto o número de identificación'),
    OpenApiParameter('cliente', bool, description='Filtrar por cliente'),
    OpenApiParameter('proveedor', bool, description='Filtrar por proveedor'),
    OpenApiParameter('empleado', bool, description='Filtrar por empleado'),
    OpenApiParameter('conductor', bool, description='Filtrar por conductor'),
]


@extend_schema(tags=['Contacto'])
class GenContactoViewSet(
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
    serializer_class = GenContactoSerializer
    serializer_class_exportar = GenContactoExportarSerializer
    serializer_class_importar = GenContactoImportarSerializer

    def get_queryset(self):
        qs = GenContacto.objects.select_related(
            'identificacion', 'ciudad', 'tipo_persona', 'responsabilidad', 'banco',
        ).order_by('nombre_corto')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre_corto__icontains=search) | qs.filter(
                numero_identificacion__icontains=search
            )

        for filtro in ('cliente', 'proveedor', 'empleado', 'conductor'):
            valor = self.request.query_params.get(filtro)
            if valor is not None:
                qs = qs.filter(**{filtro: valor.lower() == 'true'})

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenContactoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenContacto.objects.order_by('nombre_corto')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre_corto__icontains=search) | qs.filter(
                numero_identificacion__icontains=search
            )
        pagina = self.paginate_queryset(qs)
        serializer = GenContactoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter('identificacion_id', str, required=True),
            OpenApiParameter('numero_identificacion', str, required=True),
        ]
    )
    @action(detail=False, methods=['get'], url_path='consulta-dian')
    def consulta_dian(self, request):
        identificacion_id = request.query_params.get('identificacion_id')
        numero_identificacion = request.query_params.get('numero_identificacion')
        if not identificacion_id or not numero_identificacion:
            return Response(
                {'mensaje': 'identificacion_id y numero_identificacion son requeridos', 'codigo': 1},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            identificacion_id = int(identificacion_id)
        except ValueError:
            return Response(
                {'mensaje': 'identificacion_id debe ser un número entero', 'codigo': 1},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if identificacion_id not in (3, 6):
            return Response(
                {'mensaje': 'Solo se pueden autocompletar NIT o Cédula', 'codigo': 1},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            identificacion = GenIdentificacion.objects.get(pk=identificacion_id)
        except GenIdentificacion.DoesNotExist:
            return Response(
                {'mensaje': 'Identificación no encontrada', 'codigo': 1},
                status=status.HTTP_400_BAD_REQUEST,
            )
        datos = {'nit': numero_identificacion, 'identificacion': identificacion.codigo}
        respuesta = Wolframio().contacto_consulta_nit(datos)
        if respuesta['error']:
            return Response({'mensaje': respuesta['mensaje'], 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)
        return Response(respuesta['datos'], status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def validar(self, request):
        identificacion_id = request.data.get('identificacion_id')
        numero_identificacion = request.data.get('numero_identificacion')
        if not identificacion_id or not numero_identificacion:
            return Response(
                {'detail': 'identificacion_id y numero_identificacion son requeridos'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        existe = GenContacto.objects.filter(
            identificacion_id=identificacion_id,
            numero_identificacion=numero_identificacion,
        ).exists()
        return Response({'existe': existe}, status=status.HTTP_200_OK)
