from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.servicios import factura_electronica as servicio


@extend_schema(tags=['FacturaElectronica'])
class GenFacturaElectronicaViewSet(viewsets.GenericViewSet):

    @extend_schema(request=None, responses=None)
    @action(detail=False, methods=['post'])
    def activar(self, request):
        try:
            servicio.activar()
        except servicio.ErrorFacturaElectronica as e:
            cuerpo = {'detail': e.mensaje}
            if e.detalle:
                cuerpo['errores'] = e.detalle
            return Response(cuerpo, status=e.status)

        return Response(status=status.HTTP_200_OK)
