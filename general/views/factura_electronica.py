from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.servicios import factura_electronica as servicio


@extend_schema(tags=['FacturaElectronica'])
class GenFacturaElectronicaViewSet(viewsets.GenericViewSet):

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'], url_path='crear-emisor')
    def crear_emisor(self, request):
        try:
            servicio.crear_emisor()
        except servicio.ErrorFacturaElectronica as e:
            return Response(e.cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)
