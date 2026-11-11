from django.http import Http404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from tenant_users.tenants.models import DeleteError

from seguridad.models import SegUsuarioCliente
from seguridad.serializers import SegUsuarioClienteSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Usuario-Cliente'])
class SegUsuarioClienteViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SegUsuarioClienteSerializer
    permission_classes = [IsAuthenticated]

    campos_filtrables = {'cliente_id', 'usuario_id', 'propietario', 'administrador'}
    select_related_lista = ('usuario',)
    ordenamiento_default_lista = ('usuario__nombre_corto',)

    def get_queryset(self):
        # Solo las membresías de los contenedores a los que pertenece quien
        # consulta. Sin este corte cualquier sesión listaba —y editaba— los
        # miembros de contenedores ajenos; con él, una membresía de otro
        # contenedor ni siquiera se encuentra (404).
        propios = SegUsuarioCliente.objects.filter(usuario=self.request.user).values('cliente_id')
        return SegUsuarioCliente.objects.filter(cliente_id__in=propios).select_related(
            'usuario', 'cliente',
        ).prefetch_related('grupos').order_by('usuario__nombre_corto')

    @extend_schema(
        summary='Listar usuarios de un cliente',
        description='Retorna los usuarios miembros de un cliente filtrado por cliente_id.',
        parameters=[
            OpenApiParameter('cliente_id', int, required=True, description='ID del cliente'),
        ],
        responses=SegUsuarioClienteSerializer(many=True),
    )
    @extend_schema(
        summary='Eliminar acceso de usuario a cliente',
        responses={
            204: None,
            404: OpenApiResponse(
                inline_serializer('UsuarioClienteNotFound', {'detail': serializers.CharField()}),
                description='Acceso no encontrado',
            ),
        },
    )
    def destroy(self, request, *args, **kwargs):
        try:
            membresia = self.get_object()
        except (Http404, PermissionDenied):
            return Response(
                {'detail': 'No se encontró el acceso de usuario a cliente.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Solo el propio miembro (se sale) o un administrador del contenedor (lo
        # saca). A cualquier otro se le responde igual que si la membresía no
        # existiera: un 403 confirmaría que ese id es de alguien.
        if (
            membresia.usuario_id != request.user.id
            and not membresia.cliente.es_superusuario(request.user)
        ):
            return Response(
                {'detail': 'No se encontró el acceso de usuario a cliente.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # remove_user borra también el UserTenantPermissions dentro del schema
        # del contenedor. Sin eso quedaría una fila huérfana, y como su campo
        # `profile` es OneToOne, impediría volver a invitar al mismo usuario.
        try:
            membresia.cliente.remove_user(membresia.usuario)
        except DeleteError as e:
            return Response({'detail': str(e)}, status=status.HTTP_409_CONFLICT)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary='Marcar o desmarcar administrador',
        description=(
            'Cambia `administrador` de una membresía. Owner o administrador; '
            'nunca sobre el propietario ni sobre una membresía de soporte. Sin `X-Tenant`.'
        ),
        request=inline_serializer(
            'UsuarioClienteAdministrador', {'administrador': serializers.BooleanField()},
        ),
        responses={
            200: SegUsuarioClienteSerializer,
            400: OpenApiResponse(
                inline_serializer('UsuarioClienteAdministradorError', {'detail': serializers.CharField()}),
                description='Valor inválido, membresía del propietario o de soporte',
            ),
            403: OpenApiResponse(description='Quien consulta no administra el contenedor'),
            404: OpenApiResponse(description='Membresía no encontrada'),
        },
    )
    @action(detail=True, methods=['post'], url_path='administrador')
    def administrador(self, request, pk=None):
        membresia = self.get_object()

        if not membresia.cliente.es_superusuario(request.user):
            raise PermissionDenied('Solo un administrador del contenedor puede marcar administradores.')

        valor = request.data.get('administrador')
        if not isinstance(valor, bool):
            return Response(
                {'detail': 'administrador es requerido y debe ser booleano.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if membresia.propietario:
            return Response(
                {'detail': 'El propietario no se puede marcar como administrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if membresia.soporte:
            return Response(
                {'detail': 'Un usuario de soporte no se puede marcar como administrador.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membresia.administrador = valor
        membresia.save(update_fields=['administrador'])
        return Response(SegUsuarioClienteSerializer(membresia).data)

    @action(detail=False, methods=['get'], url_path='lista-cliente')
    def lista_cliente(self, request):
        cliente_id = request.query_params.get('cliente_id')
        if not cliente_id:
            return Response({'detail': 'cliente_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(cliente_id=cliente_id)
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(SegUsuarioClienteSerializer(pagina, many=True).data)

    @extend_schema(
        summary='Miembros a los que se puede transferir el contenedor',
        description=(
            'Las membresías del contenedor que pueden recibir la propiedad en '
            '`POST /contenedor/cliente/<id>/transferir/`: todas menos la del propietario '
            'y las de soporte (los administradores sí salen). Solo el propietario; a '
            'cualquier otro, 404. Sin `X-Tenant`.'
        ),
        parameters=[
            OpenApiParameter('cliente_id', int, required=True, description='ID del cliente'),
        ],
        responses={
            200: SegUsuarioClienteSerializer(many=True),
            400: OpenApiResponse(
                inline_serializer('UsuarioClienteTransferibleError', {'detail': serializers.CharField()}),
                description='cliente_id faltante o inválido',
            ),
            404: OpenApiResponse(
                inline_serializer('UsuarioClienteTransferibleNotFound', {'detail': serializers.CharField()}),
                description='No existe el contenedor o no es su propietario',
            ),
        },
    )
    @action(detail=False, methods=['get'], url_path='transferible')
    def transferible(self, request):
        # Importado acá para no acoplar seguridad a contenedor al cargar el módulo.
        from contenedor.models import CtnCliente

        cliente_id = request.query_params.get('cliente_id', '')
        if not cliente_id.isdigit():
            return Response(
                {'detail': 'cliente_id es requerido y debe ser numérico.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Solo el propietario transfiere. Contenedor inexistente y no serlo
        # responden igual: un 403 confirmaría que ese id existe.
        cliente = CtnCliente.objects.filter(pk=cliente_id).first()
        if cliente is None or not cliente.es_propietario(request.user):
            return Response({'detail': 'Cliente no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        # Las mismas exclusiones que valida `transferir`: él mismo y el soporte.
        qs = self.get_queryset().filter(cliente=cliente).exclude(propietario=True).exclude(soporte=True)
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(SegUsuarioClienteSerializer(pagina, many=True).data)

    @extend_schema(
        summary='Membresía del usuario autenticado en un contenedor',
        description=(
            'Devuelve la membresía de quien consulta en el contenedor `schema_name`, '
            'para que el front revalide sus datos (`is_superuser`, `grupos`, '
            '`propietario`, `soporte`). El usuario sale de la sesión, nunca de un '
            'parámetro. Sin `X-Tenant`.'
        ),
        parameters=[
            OpenApiParameter('schema_name', str, required=True, description='Schema del contenedor'),
        ],
        responses={
            200: SegUsuarioClienteSerializer,
            400: OpenApiResponse(
                inline_serializer('UsuarioClienteUsuarioError', {'detail': serializers.CharField()}),
                description='schema_name faltante o inválido',
            ),
            404: OpenApiResponse(
                inline_serializer('UsuarioClienteUsuarioNotFound', {'detail': serializers.CharField()}),
                description='No existe el contenedor o no es miembro',
            ),
        },
    )
    @action(detail=False, methods=['get'], url_path='usuario')
    def usuario(self, request):
        # Importado acá para no acoplar seguridad a contenedor al cargar el módulo.
        from contenedor.models import CtnCliente

        schema_name = request.query_params.get('schema_name', '')
        if not CtnCliente.SCHEMA_NAME_VALIDO.match(schema_name):
            return Response(
                {'detail': 'schema_name es requerido y debe ser válido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Contenedor inexistente y no ser miembro responden igual: un 403
        # confirmaría que ese schema existe.
        membresia = self.get_queryset().filter(
            usuario=request.user, cliente__schema_name=schema_name,
        ).first()
        if membresia is None:
            return Response(
                {'detail': 'No se encontró el acceso de usuario a cliente.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SegUsuarioClienteSerializer(membresia).data)
