from rest_framework import viewsets

from seguridad.models import SegRol
from seguridad.serializers import SegRolSerializer


class SegRolViewSet(viewsets.ModelViewSet):
    queryset = SegRol.objects.all().prefetch_related('permisos')
    serializer_class = SegRolSerializer
