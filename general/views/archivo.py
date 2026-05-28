from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from general.models import GenArchivo
from general.serializers.archivo import GenArchivoSerializer
from utilidades.archivos import eliminar_archivo, subir_archivo

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

    def create(self, request, *args, **kwargs):
        archivo = request.FILES.get('archivo')
        modelo = request.data.get('modelo')
        objeto_id = request.data.get('objeto_id')
        archivo_tipo = request.data.get('archivo_tipo', 1)

        if archivo is None:
            return Response({'detail': 'Falta el campo "archivo".'}, status=status.HTTP_400_BAD_REQUEST)
        if not modelo or not objeto_id:
            return Response(
                {'detail': 'Los campos "modelo" y "objeto_id" son requeridos.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            instancia = subir_archivo(
                archivo,
                modelo_id=int(modelo),
                objeto_id=str(objeto_id),
                archivo_tipo_id=int(archivo_tipo),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(instancia).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        eliminar_archivo(instance)
