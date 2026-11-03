from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from seguridad.models import SegUsuarioCliente, SegUsuarioClientePermiso
from seguridad.serializers import SegUsuarioClientePermisoSerializer
from utilidades.mixins import FiltrosDinamicosMixin

_LIST_PARAMS = [
    OpenApiParameter('usuario_cliente_id', int, description='Filtrar por membresía'),
    OpenApiParameter('permiso_id', int, description='Filtrar por permiso'),
]


@extend_schema(tags=['UsuarioClientePermiso'])
class SegUsuarioClientePermisoViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Permisos personalizados de un miembro en un contenedor, de a uno.

    Se suman a los de sus grupos con `heredar_permisos`, nunca restan
    (`docs/permisos.md`). Vive en el público: sin `X-Tenant`. Cualquier miembro
    ve los de su contenedor; solo el owner los agrega o quita, y nunca a una
    membresía de soporte. No hay PUT: la fila es solo el par (miembro, permiso).
    """

    serializer_class = SegUsuarioClientePermisoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Solo las filas de los contenedores a los que pertenece quien consulta:
        # una de otro contenedor ni se encuentra (404).
        propios = SegUsuarioCliente.objects.filter(usuario=self.request.user).values('cliente_id')
        qs = SegUsuarioClientePermiso.objects.filter(
            usuario_cliente__cliente_id__in=propios,
        ).select_related(
            *SegUsuarioClientePermisoSerializer.select_related_lista, 'usuario_cliente__cliente',
        ).order_by(*SegUsuarioClientePermisoSerializer.ordenamiento_default_lista)

        for filtro in ('usuario_cliente_id', 'permiso_id'):
            valor = self.request.query_params.get(filtro)
            if valor:
                qs = qs.filter(**{filtro: valor})

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        if serializer.validated_data['usuario_cliente'].cliente.owner_id != self.request.user.id:
            raise PermissionDenied('Solo el owner del contenedor puede modificar los permisos.')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.usuario_cliente.cliente.owner_id != self.request.user.id:
            raise PermissionDenied('Solo el owner del contenedor puede modificar los permisos.')
        if instance.usuario_cliente.soporte:
            raise serializers.ValidationError(
                {'detail': 'Los permisos de un usuario de soporte no se modifican.'}
            )
        instance.delete()
