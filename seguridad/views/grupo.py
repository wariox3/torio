from drf_spectacular.utils import OpenApiParameter, extend_schema
from django.contrib.auth.models import Group
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from seguridad.serializers import SegGrupoDetalleSerializer, SegGrupoSerializer

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Grupo'])
class SegGrupoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Catálogo de grupos de permisos, para poblar el selector al invitar usuarios.

    Solo lectura: los grupos y sus permisos se declaran en `seguridad/grupos.py`
    y se aplican con `python manage.py sincronizar_grupos`.
    """

    permission_classes = [IsAuthenticated]
    queryset = Group.objects.order_by('name')

    def get_serializer_class(self):
        # El detalle incluye el desglose de permisos; el listado no, para no
        # arrastrar cientos de filas en el selector.
        if self.action == 'retrieve':
            return SegGrupoDetalleSerializer
        return SegGrupoSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('permissions__content_type')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
