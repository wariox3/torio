from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from humano.models import HumAporteContrato
from humano.serializers import HumAporteContratoExportarSerializer, HumAporteContratoSerializer
from humano.servicios import AporteError, eliminar_contrato_aporte
from utilidades.mixins import ExportarExcelMixin, FiltrosDinamicosMixin


@extend_schema(tags=['Aporte contrato'])
class HumAporteContratoViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = HumAporteContratoSerializer
    serializer_class_exportar = HumAporteContratoExportarSerializer

    def get_queryset(self):
        return HumAporteContrato.objects.select_related(
            *HumAporteContratoSerializer.select_related_lista
        )

    def destroy(self, request, *args, **kwargs):
        try:
            eliminar_contrato_aporte(self.get_object())
        except AporteError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
