from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from general.models import GenImagen
from general.serializers.imagen import GenImagenCrearSerializer, GenImagenSerializer
from general.servicios.imagen import eliminar_imagen, marcar_principal, subir_imagen

_LISTAR_PARAMS = [
    OpenApiParameter('modelo', int, description='ID de gen_modelo'),
    OpenApiParameter('objeto_id', str, description='ID del registro al que pertenece la imagen'),
]


@extend_schema(tags=['Imagen'])
class GenImagenViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenImagenSerializer
    queryset = GenImagen.objects.all()
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if (modelo := params.get('modelo')):
            qs = qs.filter(modelo_id=modelo)
        if (objeto_id := params.get('objeto_id')):
            qs = qs.filter(objeto_id=objeto_id)
        return qs

    @extend_schema(parameters=_LISTAR_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=GenImagenCrearSerializer, responses=GenImagenSerializer)
    def create(self, request, *args, **kwargs):
        entrada = GenImagenCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        try:
            instancia = subir_imagen(datos['imagen'], modelo=datos['modelo'], objeto_id=datos['objeto_id'])
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(GenImagenSerializer(instancia).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=GenImagenSerializer)
    @action(detail=True, methods=['post'])
    def principal(self, request, pk=None):
        """La deja como la imagen principal de su registro, en lugar de la que lo era."""
        instancia = self.get_object()
        marcar_principal(instancia)
        return Response(GenImagenSerializer(instancia).data)

    def perform_destroy(self, instance):
        eliminar_imagen(instance)
