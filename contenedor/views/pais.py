from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from contenedor.models import CtnPais
from contenedor.serializers import CtnPaisSerializer


@extend_schema(tags=['Pais'])
class CtnPaisViewSet(viewsets.ModelViewSet):
    serializer_class = CtnPaisSerializer
    permission_classes = [IsAuthenticated]
    queryset = CtnPais.objects.all()
