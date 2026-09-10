from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from general.models import GenConfiguracion
from general.serializers import GenConfiguracionSerializer
from general.servicios import logotipo as servicio_logotipo
from utilidades.mixins import SingletonMixin


@extend_schema(tags=['Configuracion'])
class GenConfiguracionViewSet(SingletonMixin, viewsets.GenericViewSet):
    serializer_class = GenConfiguracionSerializer
    modelo_singleton = GenConfiguracion

    @extend_schema(request=GenConfiguracionSerializer, responses=GenConfiguracionSerializer)
    @action(detail=False, methods=['patch'])
    def actualizar(self, request):
        instancia = self._obtener_instancia()
        serializer = GenConfiguracionSerializer(instancia, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        summary='Logotipo de la empresa',
        description=(
            'Devuelve `{"logotipo": "<base64>"}` con el PNG del logotipo, o '
            '`null` si el tenant no cargó ninguno. Va aparte de `obtener/` '
            'porque pesa decenas de KB y casi nunca cambia: así se puede pedir '
            'y cachear por separado.'
        ),
        responses=inline_serializer(
            name='LogotipoResponse',
            fields={'logotipo': serializers.CharField(allow_null=True)},
        ),
    )
    @action(detail=False, methods=['get'])
    def logotipo(self, request):
        instancia = self._obtener_instancia()
        return Response({'logotipo': instancia.gen_empresa_logotipo})

    @extend_schema(
        summary='Cargar logotipo de la empresa',
        description=(
            'Recibe JPG, PNG o WEBP (máx 5 MB). Cualquiera de los tres sirve: se '
            'convierte a PNG de 400 px de lado y se guarda como base64 sin el '
            'prefijo `data:`. Es el logotipo que llevan los formatos impresos. '
            'Reemplaza al anterior. Devuelve el logotipo ya convertido, para '
            'refrescar la vista sin una segunda llamada.'
        ),
        request=inline_serializer(
            name='LogotipoRequest',
            fields={'logotipo': serializers.ImageField()},
        ),
        responses=inline_serializer(
            name='LogotipoResponse',
            fields={'logotipo': serializers.CharField(allow_null=True)},
        ),
    )
    @action(
        detail=False, methods=['post'],
        url_path='cargar-logotipo', parser_classes=[MultiPartParser],
    )
    def cargar_logotipo(self, request):
        archivo = request.FILES.get('logotipo')
        if not archivo:
            return Response(
                {'logotipo': 'Este campo es requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instancia = self._obtener_instancia()
        try:
            servicio_logotipo.cargar(archivo, instancia)
        except ValueError as error:
            # Lo que es culpa del archivo sale como 400; el resto sube tal cual.
            return Response({'logotipo': str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'logotipo': instancia.gen_empresa_logotipo})

    @extend_schema(
        summary='Quitar el logotipo de la empresa',
        description=(
            'Deja el logotipo en `null`; los formatos impresos vuelven a salir '
            'con ese espacio en blanco. Es idempotente: si no había logotipo, '
            'responde 200 igual.'
        ),
        request=None,
        responses=inline_serializer(
            name='LogotipoResponse',
            fields={'logotipo': serializers.CharField(allow_null=True)},
        ),
    )
    @action(detail=False, methods=['delete'], url_path='quitar-logotipo')
    def quitar_logotipo(self, request):
        instancia = self._obtener_instancia()
        servicio_logotipo.quitar(instancia)
        return Response({'logotipo': instancia.gen_empresa_logotipo})
