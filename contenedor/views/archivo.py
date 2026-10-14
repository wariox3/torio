from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contenedor import archivo as archivo_servicio
from contenedor.serializers.archivo import CtnArchivoCrearSerializer, CtnArchivoSerializer
from seguridad.models import SegUsuarioCliente


@extend_schema(tags=['Archivo'])
class CtnArchivoViewSet(viewsets.GenericViewSet):
    serializer_class = CtnArchivoSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary='Adjuntar archivo',
        description=(
            'Adjunta un archivo a un registro del schema público, como '
            '`/general/archivo/` en el tenant: `modelo` es un id de `CtnModelo` y '
            '`objeto_id` el del registro. Solo admiten adjuntos los modelos con '
            'cliente, y solo un miembro de ese contenedor puede adjuntar.\n\n'
            'Acepta PDF, imágenes, Office, texto y CSV, de hasta 20 MB. El archivo '
            'perdura: no se borra.'
        ),
        request=CtnArchivoCrearSerializer,
        responses={
            201: CtnArchivoSerializer,
            400: OpenApiResponse(
                inline_serializer('CtnArchivoErrorSerializer', {'detail': serializers.CharField()}),
                description='Archivo inválido, o registro inexistente o ajeno',
            ),
        },
    )
    def create(self, request):
        entrada = CtnArchivoCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        modelo, objeto = datos['modelo'], datos['objeto']

        # Uno ajeno responde igual que uno que no existe: distinguirlos confirmaría
        # que el id es de otro contenedor.
        es_miembro = SegUsuarioCliente.objects.filter(
            usuario=request.user, cliente_id=objeto.cliente_id,
        ).exists()
        if not es_miembro:
            mensaje = f'No existe {modelo.nombre} con id {datos["objeto_id"]}.'
            return Response(
                {'detail': f'objeto_id: {mensaje}', 'objeto_id': [mensaje]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instancia = archivo_servicio.subir(
            datos['archivo'], modelo, objeto, datos['archivo_tipo'],
        )
        return Response(CtnArchivoSerializer(instancia).data, status=status.HTTP_201_CREATED)
