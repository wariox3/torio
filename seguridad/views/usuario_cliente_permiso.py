from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.response import Response
from tenant_users.permissions.models import UserTenantPermissions

from seguridad.models import SegUsuarioCliente
from seguridad.serializers import SegUsuarioClientePermisoSerializer

_RespuestaDetalle = inline_serializer(
    name='UsuarioClientePermisoDetailResponse',
    fields={'detail': serializers.CharField()},
)


@extend_schema(tags=['Usuario-Cliente-Permiso'])
class SegUsuarioClientePermisoViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Permisos de un usuario dentro del contenedor actual.

    Se sirve **solo** desde el urlconf de tenant (`seguridad/urls_tenant.py`), así
    que el contenedor sale del header `X-Tenant` y no de un parámetro. Eso
    también hace innecesario conmutar de schema:
    `permissions_usertenantpermissions` ya es la del tenant activo, y
    `seg_usuario_cliente` se resuelve a `public` por el search_path.

    Es una vista aparte de `SegUsuarioClienteViewSet` a propósito: aquella hace
    el CRUD de la membresía en el schema público, y ésta lee una tabla distinta,
    en otro schema, bajo una precondición distinta.

    Solo lectura: las filas de permisos las gobiernan `CtnCliente.add_user` y
    `remove_user`, para que no se desincronicen de `SegUsuarioCliente`.

    TODO: definir la restricción de acceso. Hoy hereda las permission classes
    por defecto (`EsMiembroDelTenant` + `SuscripcionVigente`), así que cualquier
    miembro del contenedor puede consultar los permisos de otro pasando su
    `usuario_id`.
    """

    serializer_class = SegUsuarioClientePermisoSerializer

    def _usuario_id(self):
        return self.request.query_params.get('usuario_id')

    def get_queryset(self):
        return SegUsuarioCliente.objects.filter(
            cliente=self.request.tenant,
            usuario_id=self._usuario_id(),
        ).select_related('usuario', 'rol')

    def get_serializer_context(self):
        """
        Añade el mapa {profile_id: UserTenantPermissions} que consume el
        serializer. Es una sola fila, pero se precargan las dos M2M para no
        disparar una consulta por grupo y otra por permiso.
        """
        contexto = super().get_serializer_context()
        contexto['permisos'] = {
            fila.profile_id: fila
            for fila in UserTenantPermissions.objects.filter(
                profile_id=self._usuario_id(),
            ).prefetch_related('groups', 'user_permissions__content_type')
        }
        return contexto

    @extend_schema(
        summary='Permisos de un usuario en este contenedor',
        description=(
            'La fila de `permissions_usertenantpermissions` del usuario indicado '
            'en el contenedor del header `X-Tenant`, con sus grupos '
            '(`..._groups`) y sus permisos directos (`..._user_permissions`).'
        ),
        parameters=[
            OpenApiParameter('usuario_id', int, required=True, description='ID de SegUsuario'),
        ],
        responses={
            200: SegUsuarioClientePermisoSerializer(many=True),
            400: OpenApiResponse(_RespuestaDetalle, description='usuario_id requerido o inválido'),
        },
    )
    def list(self, request, *args, **kwargs):
        usuario_id = self._usuario_id()
        if not usuario_id:
            return Response(
                {'detail': 'usuario_id es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not str(usuario_id).isdigit():
            # Sin esto, un valor no numérico revienta en el filtro con un 500.
            return Response(
                {'detail': 'usuario_id debe ser un número entero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)
