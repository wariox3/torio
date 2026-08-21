from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from general.servicios import factura_electronica as servicio


@extend_schema(tags=['FacturaElectronica'])
class GenFacturaElectronicaViewSet(viewsets.GenericViewSet):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'], url_path='crear-emisor')
    def crear_emisor(self, request):
        try:
            servicio.crear_emisor()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)

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
