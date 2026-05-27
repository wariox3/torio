from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated

from contenedor.formatos.factura_pdf import generar_factura_pdf
from contenedor.models import CtnMovimiento
from contenedor.serializers import CtnMovimientoSerializer


@extend_schema(tags=['Movimiento'])
class CtnMovimientoViewSet(viewsets.ModelViewSet):
    serializer_class = CtnMovimientoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return CtnMovimiento.objects.all()
        return CtnMovimiento.objects.filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    @extend_schema(
        summary='Movimientos del usuario autenticado',
        description='Retorna los movimientos del usuario autenticado, ordenados por fecha descendente.',
        responses=CtnMovimientoSerializer(many=True),
    )
    @action(detail=False, methods=['get'], url_path='lista-usuario')
    def lista_usuario(self, request):
        qs = CtnMovimiento.objects.filter(
            usuario=request.user,
        ).select_related('cliente').order_by('-fecha', '-id')
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CtnMovimientoSerializer(pagina, many=True).data)

    @extend_schema(
        summary='Imprimir factura en PDF',
        description='Genera el PDF de la factura del movimiento.',
        responses={200: OpenApiResponse(description='application/pdf')},
    )
    @action(detail=True, methods=['get'], url_path='imprimir')
    def imprimir(self, request, pk=None):
        qs = CtnMovimiento.objects.select_related(
            'cliente', 'contacto', 'contacto__identificacion',
            'contacto__ciudad', 'evento_pago',
        )
        if not request.user.is_staff:
            qs = qs.filter(usuario=request.user)
        try:
            movimiento = qs.get(pk=pk)
        except CtnMovimiento.DoesNotExist:
            raise NotFound('Movimiento no encontrado.')

        pdf_bytes = generar_factura_pdf(movimiento)
        nombre = f'factura-FAC-{movimiento.id:06d}.pdf'
        respuesta = HttpResponse(pdf_bytes, content_type='application/pdf')
        respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
        return respuesta
