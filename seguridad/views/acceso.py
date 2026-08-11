from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from seguridad.models import SegAcceso
from seguridad.serializers import SegAccesoSerializer


@extend_schema(tags=['Autenticación'])
class SegAccesoViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Historial de ingresos de la cuenta autenticada.

    Solo lectura y solo lo propio: el filtro sale de `request.user` y nunca de un
    parámetro, así que no hay forma de pedir el historial ajeno. Tampoco lo ve el
    propietario del contenedor — el login es de la cuenta, no de la organización, y
    una misma cuenta puede pertenecer a varios contenedores.

    Incluye los intentos fallidos: son justamente los que el usuario necesita ver para
    darse cuenta de que alguien está probando su clave.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SegAccesoSerializer
    queryset = SegAcceso.objects.none()  # el real lo arma get_queryset

    def get_queryset(self):
        return SegAcceso.objects.filter(usuario=self.request.user)

    @extend_schema(
        summary='Historial de ingresos',
        description='Últimos intentos de ingreso de la cuenta autenticada, del más reciente al más viejo.',
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
