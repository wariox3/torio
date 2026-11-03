from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from humano.models import HumConfiguracionProvision
from humano.serializers import (
    HumConfiguracionProvisionSeleccionarSerializer,
    HumConfiguracionProvisionSerializer,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por tipo'),
]


@extend_schema(tags=['Configuración provisión'])
class HumConfiguracionProvisionViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Catálogo de configuración de provisiones: `seleccionar`, `configuracion` y
    edición de `cuenta_debito`/`cuenta_credito`. No se crean ni se borran.
    """

    serializer_class = HumConfiguracionProvisionSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        return HumConfiguracionProvision.objects.order_by('orden', 'id')

    @extend_schema(responses=HumConfiguracionProvisionSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=None)
    def configuracion(self, request):
        """Todas las provisiones, sin paginar ni filtrar: la pantalla de configuración las muestra completas."""
        qs = self.get_queryset().select_related(*HumConfiguracionProvisionSerializer.select_related_lista)
        return Response(HumConfiguracionProvisionSerializer(qs, many=True).data)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumConfiguracionProvisionSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumConfiguracionProvision.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(tipo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumConfiguracionProvisionSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
