from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from general.models import GenDocumentoElectronicoError
from general.serializers import GenDocumentoElectronicoErrorSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['DocumentoElectronicoError'])
class GenDocumentoElectronicoErrorViewSet(FiltrosDinamicosMixin, viewsets.GenericViewSet):
    """
    Los errores del último intento de emisión de cada documento. Solo lectura: los
    escribe `documento/emitir/`. No lleva `TienePermisoModelo`: es un detalle (tipo
    `D`) y el permiso lo lleva su documento.
    """

    serializer_class = GenDocumentoElectronicoErrorSerializer
    queryset = GenDocumentoElectronicoError.objects.all()
