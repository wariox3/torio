from django.db.models import ProtectedError, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion
from venta.models import VenCaja
from venta.serializers import (
    VenCajaExportarSerializer,
    VenCajaImportarSerializer,
    VenCajaSeleccionarSerializer,
    VenCajaSerializer,
)

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o placa'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre o placa'),
    OpenApiParameter('sede_id', int, description='Solo las cajas de esta sede'),
]


def _buscar(qs, search):
    if search:
        qs = qs.filter(Q(nombre__icontains=search) | Q(placa__icontains=search))
    return qs


@extend_schema(tags=['Caja'])
class VenCajaViewSet(
    FiltrosDinamicosMixin,
    ExportarExcelMixin,
    ImportarExcelMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = VenCajaSerializer
    serializer_class_exportar = VenCajaExportarSerializer
    serializer_class_importar = VenCajaImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = VenCaja.objects.select_related('sede').order_by('nombre')
        return _buscar(qs, self.request.query_params.get('search', '').strip())

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_destroy(self, instance):
        # Los documentos la protegen (`PROTECT`): sin esto el borrado sería un 500.
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError(
                {'detail': 'La caja tiene documentos y no se puede eliminar. Desactívela.'}
            )

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=VenCajaSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        """Solo las cajas activas: una inactiva no se puede elegir para una venta nueva."""
        qs = VenCaja.objects.filter(estado_activo=True).order_by('nombre')
        qs = _buscar(qs, request.query_params.get('search', '').strip())
        sede_id = request.query_params.get('sede_id', '').strip()
        if sede_id:
            if not sede_id.isdigit():
                raise ValidationError({'detail': '`sede_id` debe ser un entero.'})
            qs = qs.filter(sede_id=int(sede_id))
        pagina = self.paginate_queryset(qs)
        serializer = VenCajaSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
