from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenUsuarioConfiguracion
from general.serializers import GenUsuarioConfiguracionSerializer


@extend_schema(tags=['Configuracion'])
class GenUsuarioConfiguracionViewSet(viewsets.GenericViewSet):
    """
    La configuración del usuario autenticado en este contenedor.

    Siempre es la de `request.user`, nunca por parámetro: nadie lee ni edita la
    de otro, ni el propietario. Por eso no pide permiso de modelo, solo ser
    miembro (los permisos por defecto).
    """

    serializer_class = GenUsuarioConfiguracionSerializer

    def _obtener_instancia(self):
        instancia, _ = (
            GenUsuarioConfiguracion.objects
            .select_related('sede', 'almacen', 'caja')
            .get_or_create(usuario_id=self.request.user.pk)
        )
        return instancia

    @extend_schema(
        summary='Mi configuración',
        description='La crea vacía en el primer acceso.',
        responses=GenUsuarioConfiguracionSerializer,
    )
    @action(detail=False, methods=['get'])
    def obtener(self, request):
        return Response(GenUsuarioConfiguracionSerializer(self._obtener_instancia()).data)

    @extend_schema(
        summary='Actualizar mi configuración',
        description='Parcial. `null` quita el valor por defecto.',
        request=GenUsuarioConfiguracionSerializer,
        responses=GenUsuarioConfiguracionSerializer,
    )
    @action(detail=False, methods=['patch'])
    def actualizar(self, request):
        serializer = GenUsuarioConfiguracionSerializer(
            self._obtener_instancia(), data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
