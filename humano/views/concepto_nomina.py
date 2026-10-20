from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action

from humano.models import HumConceptoNomina
from humano.serializers import HumConceptoNominaSeleccionarSerializer, HumConceptoNominaSerializer
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import FiltrosDinamicosMixin
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por nombre'),
]


@extend_schema(tags=['Concepto nómina'])
class HumConceptoNominaViewSet(
    FiltrosDinamicosMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Catálogo de conceptos de nómina: `seleccionar`, `lista` y edición del
    `concepto` (ver `HumConceptoNominaSerializer`). No se crean ni se borran.
    """

    serializer_class = HumConceptoNominaSerializer

    def get_queryset(self):
        return HumConceptoNomina.objects.select_related('concepto').order_by('id')

    def get_permissions(self):
        # `seleccionar` sigue con los permisos por defecto, como antes; lo demás
        # exige el permiso sobre el modelo, como cualquier administrador.
        if self.action == 'seleccionar':
            return super().get_permissions()
        return [TienePermisoModelo()]

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumConceptoNominaSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumConceptoNomina.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = HumConceptoNominaSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
