from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from seguridad.models import SegUsuarioCliente, SegUsuarioClienteGrupo
from seguridad.serializers import SegUsuarioClienteGrupoSerializer
from utilidades.mixins import FiltrosDinamicosMixin

_LIST_PARAMS = [
    OpenApiParameter('usuario_cliente_id', int, description='Filtrar por membresía'),
    OpenApiParameter('grupo_id', int, description='Filtrar por grupo'),
]


@extend_schema(tags=['UsuarioClienteGrupo'])
class SegUsuarioClienteGrupoViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Grupos de un miembro en un contenedor, de a uno.

    Con `heredar_permisos` el miembro tiene todos los permisos del grupo; sin él,
    el grupo solo pone el módulo en su menú y sus pendientes (`docs/permisos.md`).
    Vive en el público: sin `X-Tenant`. Cualquier miembro ve los de su
    contenedor; solo el owner o un administrador los agrega o quita, y nunca a una membresía de
    soporte. No hay PUT: para cambiar `heredar_permisos` se quita y se agrega.
    """

    serializer_class = SegUsuarioClienteGrupoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Solo las filas de los contenedores a los que pertenece quien consulta:
        # una de otro contenedor ni se encuentra (404).
        propios = SegUsuarioCliente.objects.filter(usuario=self.request.user).values('cliente_id')
        qs = SegUsuarioClienteGrupo.objects.filter(
            usuario_cliente__cliente_id__in=propios,
        ).select_related(
            *SegUsuarioClienteGrupoSerializer.select_related_lista, 'usuario_cliente__cliente',
        ).order_by(*SegUsuarioClienteGrupoSerializer.ordenamiento_default_lista)

        for filtro in ('usuario_cliente_id', 'grupo_id'):
            valor = self.request.query_params.get(filtro)
            if valor:
                qs = qs.filter(**{filtro: valor})

        return qs

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        if not serializer.validated_data['usuario_cliente'].cliente.es_superusuario(self.request.user):
            raise PermissionDenied('Solo un administrador del contenedor puede modificar los grupos.')
        serializer.save()

    def perform_destroy(self, instance):
        if not instance.usuario_cliente.cliente.es_superusuario(self.request.user):
            raise PermissionDenied('Solo un administrador del contenedor puede modificar los grupos.')
        if instance.usuario_cliente.soporte:
            raise serializers.ValidationError(
                {'detail': 'Los grupos de un usuario de soporte no se modifican.'}
            )
        instance.delete()
