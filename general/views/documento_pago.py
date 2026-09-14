from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenDocumentoPago
from general.serializers import GenDocumentoPagoSerializer
from general.servicios import documento_pago as documento_pago_servicio


class PagoAccionRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, help_text='Id del pago.')


@extend_schema(tags=['DocumentoPago'])
class GenDocumentoPagoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Pagos de un documento. No lleva `TienePermisoModelo`: es un detalle (tipo `D`)
    y el permiso lo lleva su documento.
    """

    serializer_class = GenDocumentoPagoSerializer

    def get_queryset(self):
        qs = GenDocumentoPago.objects.select_related('cuenta_banco')
        documento_id = self.request.query_params.get('documento_id')
        if documento_id:
            qs = qs.filter(documento_id=documento_id)
        return qs

    @extend_schema(parameters=[
        OpenApiParameter('documento_id', OpenApiTypes.INT, description='Pagos de este documento.'),
    ])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary='Registrar un pago',
        description=(
            'Registra un pago contra una cuenta bancaria y recalcula el `pago` del '
            'documento, que es la suma de sus pagos no anulados.\n\n'
            'El documento tiene que ser modificable y su tipo tiene que cobrar. La '
            'cuenta bancaria necesita cuenta contable, porque contabilizar lleva ahí '
            'el pago. Que la suma no supere el total se valida al aprobar.'
        ),
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        pago = documento_pago_servicio.registrar(
            datos['documento'].pk, datos['cuenta_banco'], datos['pago'],
        )
        return Response(self.get_serializer(pago).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary='Editar un pago de un documento modificable')
    def partial_update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)
        # Un pago no se muda de documento: sería sacarlo de un saldo y meterlo en otro.
        datos.pop('documento', None)
        pago = documento_pago_servicio.actualizar(kwargs['pk'], datos)
        return Response(self.get_serializer(pago).data)

    @extend_schema(summary='Eliminar un pago de un documento modificable')
    def destroy(self, request, *args, **kwargs):
        documento_pago_servicio.eliminar(kwargs['pk'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary='Anular un pago',
        description=(
            'Anula un pago de un documento aprobado y sin contabilizar: deja de '
            'contar en el `pago` del documento y lo pagado vuelve a quedar pendiente '
            'en cartera. La fila conserva su valor.\n\n'
            'En un documento sin aprobar el pago se elimina en vez de anularse. El '
            'pago de una nota crédito no se anula: hay que desaprobar la nota.\n\n'
            'Responde el pago anulado.'
        ),
        request=PagoAccionRequestSerializer,
        responses=GenDocumentoPagoSerializer,
    )
    @action(detail=False, methods=['post'])
    def anular(self, request):
        serializer = PagoAccionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pago = documento_pago_servicio.anular(serializer.validated_data['id'])
        return Response(self.get_serializer(pago).data, status=status.HTTP_200_OK)
