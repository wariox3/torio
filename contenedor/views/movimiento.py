from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnMovimiento
from contenedor.serializers import CtnMovimientoSerializer


@extend_schema(tags=['Movimiento'])
class CtnMovimientoViewSet(viewsets.ModelViewSet):
    serializer_class = CtnMovimientoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return CtnMovimiento.objects.all()
        return CtnMovimiento.objects.filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    @extend_schema(
        summary='Movimientos del usuario autenticado',
        description='Retorna los movimientos del usuario autenticado, ordenados por fecha descendente.',
        responses=CtnMovimientoSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='lista-usuario')
    def lista_usuario(self, request):
        qs = CtnMovimiento.objects.filter(
            usuario=request.user,
        ).select_related('cliente').order_by('-fecha', '-id')
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CtnMovimientoSerializer(pagina, many=True).data)
