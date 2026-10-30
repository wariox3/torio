from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from utilidades.carbono import TIPOS_CASO, Carbono

# Módulo «General» de carbono (`GET /api/soporte/modulo/lista`).
MODULO_GENERAL = 'GEN'
# Teléfono que se manda cuando el usuario no tiene celular en su perfil.
TELEFONO_SIN_CELULAR = '123456789'


class CasoNuevoSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=TIPOS_CASO)
    # El mismo límite que tiene la columna en carbono.
    descripcion = serializers.CharField(max_length=5000)


_Detalle = inline_serializer('MesaAyudaDetalleSerializer', {'detail': serializers.CharField()})


@extend_schema(tags=['Mesa de ayuda'])
class CtnMesaAyudaViewSet(viewsets.ViewSet):
    """
    La mesa de ayuda carbono (`utilidades/carbono.py`), una acción por operación.

    Está en el schema público porque un caso es del usuario, no de un contenedor.
    Los datos de contacto salen siempre de `request.user`, nunca del body, para
    que nadie abra casos a nombre de otro.
    """

    permission_classes = [IsAuthenticated]
    # Lo lee `ScopedRateThrottle`, que solo usan las acciones que lo piden. Va en la
    # clase porque `@action` no acepta atributos que el ViewSet no tenga.
    throttle_scope = 'mesa_ayuda_caso'

    @extend_schema(
        summary='Crear caso',
        description=(
            'Crea un caso en la mesa de ayuda, en el módulo General, con el nombre, el '
            'correo y el celular del usuario autenticado. Si no tiene celular en su '
            'perfil se manda 123456789.'
        ),
        request=CasoNuevoSerializer,
        responses={
            201: inline_serializer('MesaAyudaCasoSerializer', {'id': serializers.IntegerField()}),
            400: OpenApiResponse(_Detalle, description='Datos inválidos o carbono rechazó el caso'),
            502: OpenApiResponse(_Detalle, description='La mesa de ayuda no respondió'),
        },
    )
    @action(
        detail=False, methods=['post'], url_path='caso',
        throttle_classes=[ScopedRateThrottle],
    )
    def caso(self, request):
        serializer = CasoNuevoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        usuario = request.user
        # Carbono exige teléfono, y el celular del perfil es opcional.
        telefono = (usuario.celular or '').strip() or TELEFONO_SIN_CELULAR

        # Carbono admite 200 caracteres en `contacto` y `cliente`; `nombre_corto`, 255.
        nombre = (usuario.nombre_corto or usuario.email)[:200]
        respuesta = Carbono().caso_nuevo(
            tipo=datos['tipo'],
            contacto=nombre,
            correo=usuario.email,
            telefono=telefono,
            descripcion=datos['descripcion'],
            # Los casos de torio no son de un contenedor ni de un módulo en
            # particular, pero carbono exige los dos.
            cliente=nombre,
            modulo=MODULO_GENERAL,
        )
        if not respuesta['error']:
            return Response({'id': respuesta['datos'].get('id')}, status=status.HTTP_201_CREATED)
        # Un 400 de carbono es del caso (p. ej. la descripción) y su mensaje sirve al
        # usuario; cualquier otra cosa (token, caída, 5xx) es nuestra, y no se expone.
        if respuesta['status'] == 400:
            return Response(
                {'detail': respuesta['datos'].get('mensaje') or 'La mesa de ayuda rechazó el caso.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'detail': 'No fue posible crear el caso. Intenta de nuevo más tarde.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )
