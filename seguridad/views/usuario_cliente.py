from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from seguridad.models import SegUsuarioCliente
from seguridad.serializers import SegUsuarioClienteSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Usuario-Cliente'])
class SegUsuarioClienteViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SegUsuarioClienteSerializer
    permission_classes = [IsAuthenticated]

    campos_filtrables = {'cliente_id', 'usuario_id', 'rol_id'}
    select_related_lista = ('usuario', 'rol')
    ordenamiento_default_lista = ('usuario__nombre_corto',)

    def get_queryset(self):
        return SegUsuarioCliente.objects.select_related('usuario', 'rol').order_by(
            'usuario__nombre_corto'
        )

    @extend_schema(
        summary='Listar usuarios de un cliente',
        description='Retorna los usuarios miembros de un cliente filtrado por cliente_id.',
        parameters=[
            OpenApiParameter('cliente_id', int, required=True, description='ID del cliente'),
        ],
        responses=SegUsuarioClienteSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='lista-cliente')
    def lista_cliente(self, request):
        cliente_id = request.query_params.get('cliente_id')
        if not cliente_id:
            return Response({'detail': 'cliente_id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(cliente_id=cliente_id)
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(SegUsuarioClienteSerializer(pagina, many=True).data)
