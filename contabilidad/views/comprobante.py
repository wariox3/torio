from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action

from contabilidad.models import ConComprobante
from contabilidad.serializers import ConComprobanteSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por código o nombre'),
    OpenApiParameter(
        'permite_asiento', bool,
        description='Solo los comprobantes que admiten asiento manual (o solo los que no).',
    ),
]


@extend_schema(tags=['Comprobante'])
class ConComprobanteViewSet(viewsets.GenericViewSet):
    serializer_class = ConComprobanteSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConComprobanteSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConComprobante.objects.all()

        # Se filtra antes del `search` para que el OR de abajo salga acotado a los
        # comprobantes permitidos y no los recupere por nombre.
        valor = request.query_params.get('permite_asiento')
        if valor is not None:
            qs = qs.filter(permite_asiento=valor.lower() == 'true')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(codigo__icontains=search) | qs.filter(nombre__icontains=search)
        pagina = self.paginate_queryset(qs)
        serializer = ConComprobanteSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
