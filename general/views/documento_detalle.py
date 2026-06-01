from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenDocumentoDetalle, GenModalidad, GenSector
from general.serializers import GenDocumentoDetalleSerializer
from general.servicios import LiquidadorSupervigilancia
from utilidades.mixins import FiltrosDinamicosMixin


class CalcularPrecioSupervigilanciaRequestSerializer(serializers.Serializer):
    hora_desde = serializers.TimeField()
    hora_hasta = serializers.TimeField()
    modalidad_id = serializers.IntegerField()
    sector_id = serializers.IntegerField()
    precio_adicional = serializers.DecimalField(max_digits=20, decimal_places=2, default=0)
    lunes = serializers.BooleanField(default=False)
    martes = serializers.BooleanField(default=False)
    miercoles = serializers.BooleanField(default=False)
    jueves = serializers.BooleanField(default=False)
    viernes = serializers.BooleanField(default=False)
    sabado = serializers.BooleanField(default=False)
    domingo = serializers.BooleanField(default=False)
    festivo = serializers.BooleanField(default=False)


@extend_schema(tags=['DocumentoDetalle'])
class GenDocumentoDetalleViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenDocumentoDetalleSerializer

    def get_queryset(self):
        return GenDocumentoDetalle.objects.select_related(
            *GenDocumentoDetalleSerializer.select_related_lista
        )

    @extend_schema(request=CalcularPrecioSupervigilanciaRequestSerializer)
    @action(detail=False, methods=['post'], url_path='calcular-precio-supervigilancia')
    def calcular_precio_supervigilancia(self, request):
        serializer = CalcularPrecioSupervigilanciaRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data

        try:
            sector = GenSector.objects.get(pk=datos['sector_id'])
        except GenSector.DoesNotExist:
            return Response({'mensaje': 'Sector no encontrado', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)
        try:
            modalidad = GenModalidad.objects.get(pk=datos['modalidad_id'])
        except GenModalidad.DoesNotExist:
            return Response({'mensaje': 'Modalidad no encontrada', 'codigo': 1}, status=status.HTTP_400_BAD_REQUEST)

        resultado = LiquidadorSupervigilancia.calcular_precio(
            hora_desde=datos['hora_desde'],
            hora_hasta=datos['hora_hasta'],
            sector=sector,
            modalidad=modalidad,
            precio_adicional=datos['precio_adicional'],
            lunes=datos['lunes'],
            martes=datos['martes'],
            miercoles=datos['miercoles'],
            jueves=datos['jueves'],
            viernes=datos['viernes'],
            sabado=datos['sabado'],
            domingo=datos['domingo'],
            festivo=datos['festivo'],
        )
        return Response(resultado, status=status.HTTP_200_OK)
