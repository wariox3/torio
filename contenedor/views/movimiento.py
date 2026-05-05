from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
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
