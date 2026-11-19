from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenConfiguracionUsuario
from general.serializers import GenConfiguracionUsuarioSerializer


@extend_schema(tags=['Configuracion'])
class GenConfiguracionUsuarioViewSet(viewsets.GenericViewSet):
    """
    La configuración del usuario autenticado en este contenedor.

    Siempre es la de `request.user`, nunca por parámetro: nadie lee ni edita la
    de otro, ni el propietario. Por eso no pide permiso de modelo, solo ser
    miembro (los permisos por defecto).
    """

    serializer_class = GenConfiguracionUsuarioSerializer

    def _obtener_instancia(self):
        instancia, _ = (
            GenConfiguracionUsuario.objects
            .select_related('sede', 'almacen', 'caja')
            .get_or_create(usuario_id=self.request.user.pk)
        )
        return instancia

    @extend_schema(
        summary='Mi configuración',
        description='La crea vacía en el primer acceso.',
        responses=GenConfiguracionUsuarioSerializer,
    )
    @action(detail=False, methods=['get'])
    def obtener(self, request):
        return Response(GenConfiguracionUsuarioSerializer(self._obtener_instancia()).data)

    @extend_schema(
        summary='Actualizar mi configuración',
        description='Parcial. `null` quita el valor por defecto.',
        request=GenConfiguracionUsuarioSerializer,
        responses=GenConfiguracionUsuarioSerializer,
    )
    @action(detail=False, methods=['patch'])
    def actualizar(self, request):
        serializer = GenConfiguracionUsuarioSerializer(
            self._obtener_instancia(), data=request.data, partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
