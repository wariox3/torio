from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenContacto
from general.serializers import GenContactoSerializer
from utilidades.mixins import FiltrosDinamicosMixin

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
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenContactoSerializer

    campos_filtrables = {
        'id', 'nombre_corto', 'numero_identificacion', 'cliente', 'proveedor', 'empleado', 'conductor', 'ciudad_id',
    }
    select_related_lista = ('identificacion', 'ciudad', 'tipo_persona')
    ordenamiento_default_lista = ('nombre_corto',)

    def get_queryset(self):
        qs = GenContacto.objects.select_related(
            'identificacion', 'ciudad', 'tipo_persona',
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
