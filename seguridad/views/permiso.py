from rest_framework import viewsets

from seguridad.models import SegPermiso
from seguridad.serializers import SegPermisoSerializer


class SegPermisoViewSet(viewsets.ReadOnlyModelViewSet):
    """Catálogo de permisos. Solo lectura — los permisos se definen por código."""
    queryset = SegPermiso.objects.all()
    serializer_class = SegPermisoSerializer
