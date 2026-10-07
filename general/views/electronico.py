from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from general.servicios import factura_electronica as servicio


class EmisorReasignarRequestSerializer(serializers.Serializer):
    emisor = serializers.IntegerField(min_value=1, help_text='Id del emisor en rededoc.')


@extend_schema(tags=['Electronico'])
class GenElectronicoViewSet(viewsets.GenericViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'], url_path='emisor-crear')
    def emisor_crear(self, request):
        try:
            servicio.emisor_crear()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'], url_path='emisor-consultar')
    def emisor_consultar(self, request):
        try:
            datos = servicio.emisor_consultar()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['patch'], url_path='emisor-actualizar')
    def emisor_actualizar(self, request):
        try:
            datos = servicio.emisor_actualizar()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(request=EmisorReasignarRequestSerializer, responses=None)
    @action(detail=False, methods=['post'], url_path='emisor-reasignar')
    def emisor_reasignar(self, request):
        serializer = EmisorReasignarRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            servicio.emisor_reasignar(serializer.validated_data['emisor'])
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'], url_path='emisor-desvincular')
    def emisor_desvincular(self, request):
        try:
            servicio.emisor_desvincular()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=['get'], url_path='certificado-consultar')
    def certificado_consultar(self, request):
        try:
            datos = servicio.certificado_consultar()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(datos, status=status.HTTP_200_OK)

    @extend_schema(
        request={'multipart/form-data': {
            'type': 'object',
            'properties': {
                'archivo': {'type': 'string', 'format': 'binary'},
                'clave': {'type': 'string'},
            },
            'required': ['archivo', 'clave'],
        }},
        responses=None,
    )
    @action(detail=False, methods=['post'], url_path='cargar-certificado')
    def cargar_certificado(self, request):
        try:
            servicio.cargar_certificado(request.FILES.get('archivo'), request.data.get('clave'))
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)
