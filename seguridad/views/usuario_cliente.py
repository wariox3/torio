from django.db import transaction
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

from contenedor.models import CtnAplicacion
from seguridad.models import SegUsuarioCliente, SegUsuarioClienteAplicacion
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

    campos_filtrables = {'cliente_id', 'usuario_id', 'propietario'}
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
        ).prefetch_related('aplicaciones').order_by('usuario__nombre_corto')

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

        # Solo el propio miembro (se sale) o el owner del contenedor (lo saca).
        # A cualquier otro se le responde igual que si la membresía no existiera:
        # un 403 confirmaría que ese id es de alguien.
        if request.user.id not in (membresia.usuario_id, membresia.cliente.owner_id):
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

    @action(detail=False, methods=['get'], url_path='lista-cliente')
    def lista_cliente(self, request):
        cliente_id = request.query_params.get('cliente_id')
        if not cliente_id:
            return Response({'detail': 'cliente_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(cliente_id=cliente_id)
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(SegUsuarioClienteSerializer(pagina, many=True).data)

    @extend_schema(
        summary='Aplicaciones de un miembro',
        description=(
            'GET: todas las aplicaciones del catálogo, con `activa` según lo que ve este '
            'miembro en el contenedor. PUT `{"aplicaciones": [ids]}`: las reemplaza '
            '(una lista vacía las quita todas) y responde como el GET. Solo el owner '
            'del contenedor las edita, y no a una membresía de soporte.'
        ),
        request=inline_serializer('SegUsuarioClienteAplicacionActualizar', {
            'aplicaciones': serializers.ListField(child=serializers.IntegerField()),
        }),
        responses=inline_serializer('SegUsuarioClienteAplicacion', {
            'aplicacion_id': serializers.IntegerField(),
            'aplicacion_nombre': serializers.CharField(),
            'activa': serializers.BooleanField(),
        }, many=True),
    )
    @action(detail=True, methods=['get', 'put'], url_path='aplicacion')
    def aplicacion(self, request, pk=None):
        try:
            membresia = self.get_object()
        except (Http404, PermissionDenied):
            return Response(
                {'detail': 'No se encontró el acceso de usuario a cliente.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == 'PUT':
            # Es 403 y no 404: quien llega acá ya es miembro y puede ver la fila.
            if membresia.cliente.owner_id != request.user.id:
                return Response(
                    {'detail': 'Solo el owner del contenedor puede modificar las aplicaciones.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # El soporte entra con todas; el owner puede sacarlo, no recortarlo.
            if membresia.soporte:
                return Response(
                    {'detail': 'Las aplicaciones de un usuario de soporte no se modifican.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            aplicaciones = request.data.get('aplicaciones') if isinstance(request.data, dict) else None
            if not isinstance(aplicaciones, list) or not all(
                isinstance(a, int) and not isinstance(a, bool) for a in aplicaciones
            ):
                return Response(
                    {'detail': 'aplicaciones debe ser una lista de ids.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            ids = set(aplicaciones)
            inexistentes = ids - set(
                CtnAplicacion.objects.filter(id__in=ids).values_list('id', flat=True)
            )
            if inexistentes:
                return Response(
                    {'detail': 'Aplicaciones inexistentes: '
                     + ', '.join(map(str, sorted(inexistentes))) + '.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                SegUsuarioClienteAplicacion.objects.filter(
                    usuario_cliente=membresia,
                ).exclude(aplicacion_id__in=ids).delete()
                SegUsuarioClienteAplicacion.objects.bulk_create(
                    [SegUsuarioClienteAplicacion(usuario_cliente=membresia, aplicacion_id=i) for i in ids],
                    ignore_conflicts=True,
                )

        activas = set(
            SegUsuarioClienteAplicacion.objects.filter(
                usuario_cliente=membresia,
            ).values_list('aplicacion_id', flat=True)
        )
        return Response([
            {'aplicacion_id': a.id, 'aplicacion_nombre': a.nombre, 'activa': a.id in activas}
            for a in CtnAplicacion.objects.order_by('id')
        ])
