from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from humano.models import HumLiquidacionAdicional
from humano.serializers import HumLiquidacionAdicionalSerializer
from humano.serializers.liquidacion import MENSAJE_LIQUIDACION_CERRADA
from humano.servicios import actualizar_totales
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Liquidación adicional'])
class HumLiquidacionAdicionalViewSet(
    FiltrosDinamicosMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumLiquidacionAdicionalSerializer

    def get_queryset(self):
        return HumLiquidacionAdicional.objects.select_related(
            *HumLiquidacionAdicionalSerializer.select_related_lista
        )

    def perform_create(self, serializer):
        # El adicional mueve los totales de la liquidación.
        with transaction.atomic():
            adicional = serializer.save()
            actualizar_totales(adicional.liquidacion_id)

    def destroy(self, request, *args, **kwargs):
        adicional = self.get_object()
        liquidacion = adicional.liquidacion
        if liquidacion.estado_generado or liquidacion.estado_aprobado:
            return Response({'detail': MENSAJE_LIQUIDACION_CERRADA}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            adicional.delete()
            actualizar_totales(liquidacion.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
