from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.servicios import plantilla as servicio


@extend_schema(tags=['Plantilla'])
class GenPlantillaViewSet(viewsets.GenericViewSet):
    """
    Carga de plantillas de datos de arranque.

    Opera sobre el contenedor del que viene la petición: el schema sale de
    `connection.schema_name`, que fija `TenantHeaderMiddleware` con el header
    `X-Tenant`, y no de un parámetro. Así no hay forma de sembrar el contenedor
    de otro.

    Las dos acciones apagan `gen_asistente_datos_iniciales` y devuelven su nuevo
    valor, para que el front no tenga que volver a pedir el parámetro solo para
    ocultar el asistente. Escribir ese campo pasa por acá y no por un PATCH a
    `GenParametro`, que es de solo lectura a propósito.
    """

    @extend_schema(
        summary='Cargar plantilla',
        description=(
            'Inserta en este contenedor los datos de una plantilla de '
            '`general/plantillas/`. Es todo o nada: si una inserción falla no queda '
            'nada. Devuelve las filas insertadas por modelo.'
        ),
        request=inline_serializer(
            'GenPlantillaCargarSerializer',
            {'archivo': serializers.CharField(help_text='Ej.: 01_general.json')},
        ),
        responses={
            200: OpenApiResponse(
                inline_serializer(
                    'GenPlantillaResumenSerializer',
                    {'modelos': serializers.DictField(child=serializers.IntegerField())},
                ),
                description='Filas insertadas por modelo',
            ),
            400: OpenApiResponse(
                inline_serializer(
                    'GenPlantillaErrorSerializer', {'detail': serializers.CharField()},
                ),
                description=(
                    'Plantilla inexistente, mal formada, que no se pudo aplicar, o '
                    'contenedor que ya pasó por el asistente'
                ),
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='cargar')
    def cargar(self, request):
        archivo = str(request.data.get('archivo') or '').strip()
        if not archivo:
            return Response(
                {'detail': 'Falta el nombre del archivo de la plantilla.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            modelos = servicio.aplicar(connection.schema_name, archivo)
        except servicio.PlantillaError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {'modelos': modelos, 'gen_asistente_datos_iniciales': False},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary='Descartar el asistente de datos iniciales',
        description=(
            'Apaga `gen_asistente_datos_iniciales` sin cargar nada: el usuario '
            'decidió no usar plantilla. Es idempotente y no tiene vuelta atrás '
            'desde la API.'
        ),
        request=None,
        responses={
            200: OpenApiResponse(
                inline_serializer(
                    'GenPlantillaDescartarSerializer',
                    {'gen_asistente_datos_iniciales': serializers.BooleanField()},
                ),
                description='Asistente apagado',
            ),
        },
    )
    @action(detail=False, methods=['post'], url_path='descartar')
    def descartar(self, request):
        servicio.descartar(connection.schema_name)
        return Response(
            {'gen_asistente_datos_iniciales': False}, status=status.HTTP_200_OK,
        )
