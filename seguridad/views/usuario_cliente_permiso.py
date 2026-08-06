from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from tenant_users.permissions.models import UserTenantPermissions

from seguridad.models import SegUsuarioCliente
from seguridad.serializers import (
    SegGrupoSerializer,
    SegGrupoUsuarioSerializer,
    SegPermisoSerializer,
    SegPermisoUsuarioSerializer,
    SegUsuarioClientePermisoSerializer,
)

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

    Las filas en sí (alta y baja) las gobiernan `CtnCliente.add_user` y
    `remove_user`, para que no se desincronicen de `SegUsuarioCliente`. Acá solo
    se leen, y se agregan o quitan grupos sobre una fila existente.

    TODO: definir la restricción de LECTURA. Hoy hereda las permission classes
    por defecto (`EsMiembroDelTenant` + `SuscripcionVigente`), así que cualquier
    miembro del contenedor puede consultar los permisos de otro pasando su
    `usuario_id`. La escritura sí está restringida al owner.
    """

    serializer_class = SegUsuarioClientePermisoSerializer

    def _usuario_id(self):
        return self.request.query_params.get('usuario_id')

    def get_queryset(self):
        return SegUsuarioCliente.objects.filter(
            cliente=self.request.tenant,
            usuario_id=self._usuario_id(),
        ).select_related('usuario', 'rol').order_by('id')

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

    @extend_schema(
        summary='Agregar un grupo a un usuario en este contenedor',
        request=SegGrupoUsuarioSerializer,
        responses={
            200: SegGrupoSerializer(many=True),
            403: OpenApiResponse(_RespuestaDetalle, description='No eres el owner'),
            404: OpenApiResponse(_RespuestaDetalle, description='El usuario no es miembro'),
            409: OpenApiResponse(
                _RespuestaDetalle,
                description='El usuario ya tiene el grupo, o la membresía no tiene permisos creados',
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='agregar-grupo')
    def agregar_grupo(self, request):
        """
        Agrega un grupo al usuario.

        No es idempotente a propósito: si el usuario ya tiene el grupo se
        responde 409 en vez de dejarlo pasar en silencio, para que el front
        pueda avisar que la asignación ya existía.
        """
        # Cambiar permisos es potestad del dueño del contenedor, igual que
        # invitar (ver CtnInvitacionViewSet.create). Sin esto, cualquier miembro
        # podría auto-asignarse cualquier grupo.
        if request.tenant.owner_id != request.user.id:
            return Response(
                {'detail': 'Solo el owner del contenedor puede cambiar los grupos.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializador = SegGrupoUsuarioSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        usuario_id = serializador.validated_data['usuario_id']
        grupo = serializador.validated_data['grupo']

        if not SegUsuarioCliente.objects.filter(
            cliente=request.tenant, usuario_id=usuario_id,
        ).exists():
            return Response(
                {'detail': 'El usuario no es miembro de este contenedor.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        permisos = UserTenantPermissions.objects.filter(profile_id=usuario_id).first()
        if permisos is None:
            return Response(
                {'detail': 'La membresía no tiene permisos creados; debió crearse con add_user.'},
                status=status.HTTP_409_CONFLICT,
            )

        if permisos.groups.filter(pk=grupo.pk).exists():
            return Response(
                {'detail': f'El usuario ya tiene el grupo "{grupo.name}".'},
                status=status.HTTP_409_CONFLICT,
            )

        permisos.groups.add(grupo)
        return Response(SegGrupoSerializer(permisos.groups.all(), many=True).data)

    @extend_schema(
        summary='Quitar un grupo a un usuario en este contenedor',
        request=SegGrupoUsuarioSerializer,
        responses={
            200: SegGrupoSerializer(many=True),
            403: OpenApiResponse(_RespuestaDetalle, description='No eres el owner'),
            404: OpenApiResponse(_RespuestaDetalle, description='El usuario no es miembro'),
            409: OpenApiResponse(
                _RespuestaDetalle,
                description='El usuario no tiene el grupo, o la membresía no tiene permisos creados',
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='quitar-grupo')
    def quitar_grupo(self, request):
        """
        Quita un grupo al usuario.

        No es idempotente a propósito: si el usuario no tiene el grupo se
        responde 409 en vez de dejarlo pasar en silencio, igual que hace
        `agregar_grupo` con el caso contrario.
        """
        # Cambiar permisos es potestad del dueño del contenedor, igual que
        # invitar (ver CtnInvitacionViewSet.create). Sin esto, cualquier miembro
        # podría quitarle grupos a otro.
        if request.tenant.owner_id != request.user.id:
            return Response(
                {'detail': 'Solo el owner del contenedor puede cambiar los grupos.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializador = SegGrupoUsuarioSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        usuario_id = serializador.validated_data['usuario_id']
        grupo = serializador.validated_data['grupo']

        if not SegUsuarioCliente.objects.filter(
            cliente=request.tenant, usuario_id=usuario_id,
        ).exists():
            return Response(
                {'detail': 'El usuario no es miembro de este contenedor.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        permisos = UserTenantPermissions.objects.filter(profile_id=usuario_id).first()
        if permisos is None:
            return Response(
                {'detail': 'La membresía no tiene permisos creados; debió crearse con add_user.'},
                status=status.HTTP_409_CONFLICT,
            )

        if not permisos.groups.filter(pk=grupo.pk).exists():
            return Response(
                {'detail': f'El usuario no tiene el grupo "{grupo.name}".'},
                status=status.HTTP_409_CONFLICT,
            )

        permisos.groups.remove(grupo)
        return Response(SegGrupoSerializer(permisos.groups.all(), many=True).data)

    @extend_schema(
        summary='Agregar un permiso individual a un usuario en este contenedor',
        description=(
            'Escribe en `permissions_usertenantpermissions_user_permissions`: el '
            'permiso queda concedido a la persona directamente, al margen de sus '
            'grupos.'
        ),
        request=SegPermisoUsuarioSerializer,
        responses={
            200: SegPermisoSerializer(many=True),
            403: OpenApiResponse(_RespuestaDetalle, description='No eres el owner'),
            404: OpenApiResponse(_RespuestaDetalle, description='El usuario no es miembro'),
            409: OpenApiResponse(
                _RespuestaDetalle,
                description='El usuario ya tiene el permiso, o la membresía no tiene permisos creados',
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='agregar-permiso')
    def agregar_permiso(self, request):
        """
        Agrega un permiso individual al usuario.

        No es idempotente a propósito: si el usuario ya lo tiene se responde 409
        en vez de dejarlo pasar en silencio.
        """
        # Cambiar permisos es potestad del dueño del contenedor, igual que
        # invitar (ver CtnInvitacionViewSet.create). Sin esto, cualquier miembro
        # podría auto-asignarse cualquier permiso.
        if request.tenant.owner_id != request.user.id:
            return Response(
                {'detail': 'Solo el owner del contenedor puede cambiar los permisos.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializador = SegPermisoUsuarioSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        usuario_id = serializador.validated_data['usuario_id']
        permiso = serializador.validated_data['permiso']

        if not SegUsuarioCliente.objects.filter(
            cliente=request.tenant, usuario_id=usuario_id,
        ).exists():
            return Response(
                {'detail': 'El usuario no es miembro de este contenedor.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        permisos = UserTenantPermissions.objects.filter(profile_id=usuario_id).first()
        if permisos is None:
            return Response(
                {'detail': 'La membresía no tiene permisos creados; debió crearse con add_user.'},
                status=status.HTTP_409_CONFLICT,
            )

        if permisos.user_permissions.filter(pk=permiso.pk).exists():
            return Response(
                {'detail': f'El usuario ya tiene el permiso "{permiso.codename}".'},
                status=status.HTTP_409_CONFLICT,
            )

        permisos.user_permissions.add(permiso)
        consulta = permisos.user_permissions.select_related('content_type')
        return Response(SegPermisoSerializer(consulta, many=True).data)

    @extend_schema(
        summary='Quitar un permiso individual a un usuario en este contenedor',
        description=(
            'Borra de `permissions_usertenantpermissions_user_permissions`. No '
            'toca los permisos que el usuario tenga por pertenecer a un grupo.'
        ),
        request=SegPermisoUsuarioSerializer,
        responses={
            200: SegPermisoSerializer(many=True),
            403: OpenApiResponse(_RespuestaDetalle, description='No eres el owner'),
            404: OpenApiResponse(_RespuestaDetalle, description='El usuario no es miembro'),
            409: OpenApiResponse(
                _RespuestaDetalle,
                description='El usuario no tiene el permiso, o la membresía no tiene permisos creados',
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='quitar-permiso')
    def quitar_permiso(self, request):
        """
        Quita un permiso individual al usuario.

        No es idempotente a propósito: si el usuario no lo tiene se responde 409,
        igual que hace `agregar_permiso` con el caso contrario.

        Solo afecta a los permisos directos. Si el permiso además le llega por un
        grupo, lo sigue teniendo: para eso hay que quitarle el grupo.
        """
        # Cambiar permisos es potestad del dueño del contenedor, igual que
        # invitar (ver CtnInvitacionViewSet.create). Sin esto, cualquier miembro
        # podría quitarle permisos a otro.
        if request.tenant.owner_id != request.user.id:
            return Response(
                {'detail': 'Solo el owner del contenedor puede cambiar los permisos.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializador = SegPermisoUsuarioSerializer(data=request.data)
        serializador.is_valid(raise_exception=True)
        usuario_id = serializador.validated_data['usuario_id']
        permiso = serializador.validated_data['permiso']

        if not SegUsuarioCliente.objects.filter(
            cliente=request.tenant, usuario_id=usuario_id,
        ).exists():
            return Response(
                {'detail': 'El usuario no es miembro de este contenedor.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        permisos = UserTenantPermissions.objects.filter(profile_id=usuario_id).first()
        if permisos is None:
            return Response(
                {'detail': 'La membresía no tiene permisos creados; debió crearse con add_user.'},
                status=status.HTTP_409_CONFLICT,
            )

        if not permisos.user_permissions.filter(pk=permiso.pk).exists():
            return Response(
                {'detail': f'El usuario no tiene el permiso "{permiso.codename}".'},
                status=status.HTTP_409_CONFLICT,
            )

        permisos.user_permissions.remove(permiso)
        consulta = permisos.user_permissions.select_related('content_type')
        return Response(SegPermisoSerializer(consulta, many=True).data)
