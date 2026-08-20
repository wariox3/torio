from django.http import HttpResponse
from django.utils.http import content_disposition_header
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from general.models import GenArchivo
from general.serializers.archivo import GenArchivoCrearSerializer, GenArchivoSerializer
from general.servicios.archivo import descargar_archivo, eliminar_archivo, subir_archivo

_LISTAR_PARAMS = [
    OpenApiParameter('modelo', int, description='ID de gen_modelo'),
    OpenApiParameter('objeto_id', str, description='ID del registro al que pertenece el archivo'),
    OpenApiParameter('archivo_tipo', int, description='ID de gen_archivo_tipo'),
]


@extend_schema(tags=['Archivo'])
class GenArchivoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenArchivoSerializer
    queryset = GenArchivo.objects.select_related('archivo_tipo', 'modelo')
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (modelo := params.get('modelo')):
            qs = qs.filter(modelo_id=modelo)
        if (objeto_id := params.get('objeto_id')):
            qs = qs.filter(objeto_id=objeto_id)
        if (archivo_tipo := params.get('archivo_tipo')):
            qs = qs.filter(archivo_tipo_id=archivo_tipo)
        return qs

    @extend_schema(parameters=_LISTAR_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=GenArchivoCrearSerializer, responses=GenArchivoSerializer)
    def create(self, request, *args, **kwargs):
        entrada = GenArchivoCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        archivo_tipo = datos['archivo_tipo']

        instancia = subir_archivo(
            datos['archivo'],
            modelo=datos['modelo'],
            objeto_id=datos['objeto_id'],
            archivo_tipo_id=archivo_tipo.pk if archivo_tipo else 1,
        )
        return Response(GenArchivoSerializer(instancia).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={
            (200, 'application/octet-stream'): OpenApiResponse(
                OpenApiTypes.BINARY, description='El contenido del archivo.',
            ),
        },
    )
    @action(detail=True, methods=['get'])
    def descargar(self, request, pk=None):
        """
        Sirve el archivo desde el back.

        El bucket es privado, así que esta es la única forma de leerlo: la URL
        directa de B2 responde 401. `get_object` usa el queryset del contenedor,
        de modo que una fila de otro tenant ni siquiera se encuentra.
        """
        instancia = self.get_object()
        contenido = descargar_archivo(instancia)

        respuesta = HttpResponse(contenido, content_type=instancia.tipo)
        # El nombre lo puso quien subió el archivo: con un f-string, unas comillas
        # o un acento romperían el header. Este helper es el que usa FileResponse.
        respuesta['Content-Disposition'] = content_disposition_header(True, instancia.nombre)
        return respuesta

    def perform_destroy(self, instance):
        eliminar_archivo(instance)
