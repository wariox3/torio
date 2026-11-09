from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from contabilidad.models import ConExogenaConcepto
from contabilidad.serializers import ConExogenaConceptoSeleccionarSerializer
from utilidades.paginacion import SeleccionarPaginacion

_SELECCIONAR_PARAMS = [
    OpenApiParameter('formato_id', int, description='Solo los conceptos de este formato'),
    OpenApiParameter('search', str, description='Buscar por código o nombre del concepto'),
]


@extend_schema(tags=['Exógena concepto'])
class ConExogenaConceptoViewSet(viewsets.GenericViewSet):
    serializer_class = ConExogenaConceptoSeleccionarSerializer

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=ConExogenaConceptoSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = ConExogenaConcepto.objects.order_by('formato_id', 'codigo')
        formato_id = request.query_params.get('formato_id', '').strip()
        if formato_id:
            if not formato_id.isdigit():
                raise ValidationError({'detail': '`formato_id` debe ser un entero.'})
            qs = qs.filter(formato_id=int(formato_id))
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(codigo__icontains=search) | Q(nombre__icontains=search))
        pagina = self.paginate_queryset(qs)
        serializer = ConExogenaConceptoSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
