from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenConfiguracion
from general.serializers import GenConfiguracionSerializer


@extend_schema(tags=['Configuracion'])
class GenConfiguracionViewSet(viewsets.GenericViewSet):
    serializer_class = GenConfiguracionSerializer

    def _obtener_instancia(self):
        instancia, _ = GenConfiguracion.objects.get_or_create(id=1)
        return instancia

    @extend_schema(responses=GenConfiguracionSerializer)
    @action(detail=False, methods=['get'])
    def obtener(self, request):
        serializer = GenConfiguracionSerializer(self._obtener_instancia())
        return Response(serializer.data)

    @extend_schema(request=GenConfiguracionSerializer, responses=GenConfiguracionSerializer)
    @action(detail=False, methods=['patch'])
    def actualizar(self, request):
        instancia = self._obtener_instancia()
        serializer = GenConfiguracionSerializer(instancia, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'campos', str,
                description='Campos separados por coma, ej: gen_uvt,hum_salario_minimo',
            ),
        ],
        responses=GenConfiguracionSerializer,
    )
    @action(detail=False, methods=['get'])
    def campos(self, request):
        solicitados = []
        for valor in request.query_params.getlist('campos'):
            solicitados.extend(c.strip() for c in valor.split(',') if c.strip())

        if not solicitados:
            return Response(
                {'detail': 'Debe indicar al menos un campo en el parámetro "campos".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        permitidos = {f.name for f in GenConfiguracion._meta.concrete_fields}
        invalidos = [c for c in solicitados if c not in permitidos]
        if invalidos:
            return Response(
                {'detail': f'Campos no válidos: {", ".join(invalidos)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        self._obtener_instancia()  # garantiza que la fila id=1 exista
        # quita duplicados preservando el orden solicitado
        unicos = list(dict.fromkeys(solicitados))
        datos = GenConfiguracion.objects.filter(id=1).values(*unicos).first()
        return Response(datos)
