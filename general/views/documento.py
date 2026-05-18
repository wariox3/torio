from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from general.models import GenDocumento
from general.serializers import GenDocumentoSerializer
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Documento'])
class GenDocumentoViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenDocumentoSerializer

    campos_filtrables = {
        'id', 'numero', 'fecha', 'documento_tipo_id', 'contacto_id',
        'estado_aprobado', 'estado_anulado', 'estado_contabilizado',
    }
    select_related_lista = ('documento_tipo', 'contacto')
    prefetch_related_lista = ('documentos_detalles_documento_rel',)
    ordenamiento_default_lista = ('-fecha', '-numero')

    def get_queryset(self):
        return GenDocumento.objects.select_related(
            'documento_tipo', 'contacto',
        ).prefetch_related(
            'documentos_detalles_documento_rel',
        )
