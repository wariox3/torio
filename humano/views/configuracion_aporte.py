from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from humano.models import HumConfiguracionAporte
from humano.serializers import (
    HumConfiguracionAporteSeleccionarSerializer,
    HumConfiguracionAporteSerializer,
)
from seguridad.permissions import TienePermisoModelo
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por tipo'),
]


@extend_schema(tags=['Configuración aporte'])
class HumConfiguracionAporteViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Catálogo de configuración de aportes: `seleccionar`, `configuracion` y
    edición de la `cuenta`. No se crean ni se borran.
    """

    serializer_class = HumConfiguracionAporteSerializer

    def get_queryset(self):
        return HumConfiguracionAporte.objects.order_by('orden', 'id')

    def get_permissions(self):
        # `seleccionar` sigue con los permisos por defecto, como antes; lo demás
        # exige el permiso sobre el modelo (ver o editar).
        if self.action == 'seleccionar':
            return super().get_permissions()
        return [TienePermisoModelo()]

    @extend_schema(responses=HumConfiguracionAporteSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=None)
    def configuracion(self, request):
        """Todos los aportes, sin paginar ni filtrar: la pantalla de configuración los muestra completos."""
        qs = self.get_queryset().select_related(*HumConfiguracionAporteSerializer.select_related_lista)
        return Response(HumConfiguracionAporteSerializer(qs, many=True).data)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumConfiguracionAporteSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumConfiguracionAporte.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(tipo__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumConfiguracionAporteSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
