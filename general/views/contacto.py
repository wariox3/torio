from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenContacto, GenIdentificacion
from general.serializers import (
    GenContactoExportarSerializer,
    GenContactoImportarSerializer,
    GenContactoSeleccionarSerializer,
    GenContactoSerializer,
)
from general.servicios import factura_electronica as factura_electronica_servicio
from general.servicios.imagen import anotar_imagen_principal, eliminar_imagenes_de
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre corto o número de identificación'),
    OpenApiParameter('cliente', bool, description='Filtrar por cliente'),
    OpenApiParameter('proveedor', bool, description='Filtrar por proveedor'),
    OpenApiParameter('empleado', bool, description='Filtrar por empleado'),
    OpenApiParameter('conductor', bool, description='Filtrar por conductor'),
    OpenApiParameter('estado_inactivo', bool, description='Filtrar por inactivo'),
]

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre corto o número de identificación'),
    OpenApiParameter('cliente', bool, description='Filtrar por cliente'),
    OpenApiParameter('proveedor', bool, description='Filtrar por proveedor'),
    OpenApiParameter('empleado', bool, description='Filtrar por empleado'),
    OpenApiParameter('conductor', bool, description='Filtrar por conductor'),
    OpenApiParameter('estado_inactivo', bool, description='Filtrar por inactivo'),
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
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = GenContacto.objects.select_related(
            'identificacion', 'ciudad', 'ciudad__estado', 'tipo_persona', 'responsabilidad',
            'banco', 'asesor', 'precio', 'plazo_pago', 'plazo_pago_proveedor',
        ).order_by('nombre_corto')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre_corto__icontains=search) | qs.filter(
                numero_identificacion__icontains=search
            )

        for filtro in ('cliente', 'proveedor', 'empleado', 'conductor', 'estado_inactivo'):
            valor = self.request.query_params.get(filtro)
            if valor is not None:
                qs = qs.filter(**{filtro: valor.lower() == 'true'})

        return anotar_imagen_principal(qs)

    def perform_destroy(self, instance):
        pk = instance.pk
        instance.delete()
        eliminar_imagenes_de(GenContacto, pk)

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=GenContactoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = GenContacto.objects.select_related(
            'ciudad', 'plazo_pago', 'plazo_pago_proveedor',
        ).order_by('nombre_corto')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre_corto__icontains=search) | qs.filter(
                numero_identificacion__icontains=search
            )

        for filtro in ('cliente', 'proveedor', 'empleado', 'conductor', 'estado_inactivo'):
            valor = request.query_params.get(filtro)
            if valor is not None:
                qs = qs.filter(**{filtro: valor.lower() == 'true'})

        pagina = self.paginate_queryset(qs)
        serializer = GenContactoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        description=(
            'Consulta en la DIAN, a través de rededoc, el nombre y el correo registrados '
            'para un documento. Si no existe responde 200 con `existe: false`. Solo '
            'funciona en producción: en habilitación la DIAN no tiene adquirientes. '
            '400 si faltan datos o la identificación no existe; 502 si rededoc o la DIAN fallan.'
        ),
        request=inline_serializer('ContactoConsultaDian', {
            'identificacion_id': serializers.IntegerField(),
            'numero_identificacion': serializers.CharField(),
        }),
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=['post'], url_path='consulta-dian')
    def consulta_dian(self, request):
        identificacion_id = request.data.get('identificacion_id')
        numero_identificacion = str(request.data.get('numero_identificacion') or '').strip()
        if not identificacion_id or not numero_identificacion:
            return Response(
                {'detail': 'identificacion_id y numero_identificacion son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        identificacion = None
        if str(identificacion_id).isdigit():
            identificacion = GenIdentificacion.objects.filter(pk=identificacion_id).first()
        if identificacion is None:
            return Response(
                {'detail': f'La identificación {identificacion_id} no existe.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            datos = factura_electronica_servicio.consultar_adquiriente(
                identificacion, numero_identificacion,
            )
        except factura_electronica_servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)
        return Response(datos, status=status.HTTP_200_OK)

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
