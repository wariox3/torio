from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle

from seguridad.models import SegUsuario
from seguridad.serializers import SegUsuarioSerializer


class SegUsuarioViewSet(viewsets.ModelViewSet):
    queryset = SegUsuario.objects.all()
    serializer_class = SegUsuarioSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [AllowAny()]
        return super().get_permissions()

    def get_throttles(self):
        if self.action == 'create':
            self.throttle_scope = 'registro'
            return [ScopedRateThrottle()]
        return super().get_throttles()
