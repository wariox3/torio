from rest_framework import viewsets

from seguridad.models import SegUsuarioRol
from seguridad.serializers import SegUsuarioRolSerializer


class SegUsuarioRolViewSet(viewsets.ModelViewSet):
    queryset = SegUsuarioRol.objects.select_related('usuario', 'rol', 'tenant')
    serializer_class = SegUsuarioRolSerializer
