from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from general.models import GenCuentaBanco
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import FiltrosDinamicosMixin
from venta.models import VenTurno
from venta.serializers import (
    VenTurnoAbrirRequestSerializer,
    VenTurnoCerrarRequestSerializer,
    VenTurnoConDetallesSerializer,
    VenTurnoResumenSerializer,
    VenTurnoSerializer,
)
from venta.servicios import turno as turno_servicio
from venta.servicios import turno_imprimir


@extend_schema(tags=['Turno'])
class VenTurnoViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Los turnos no tienen crear/editar/eliminar: se abren con `abrir` y se cierran
    con `cerrar`, que es donde viven las reglas (ver `venta/servicios/turno.py`).
    """

    serializer_class = VenTurnoSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        return VenTurno.objects.select_related(*VenTurnoSerializer.select_related_lista)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return VenTurnoConDetallesSerializer
        return VenTurnoSerializer

    def retrieve(self, request, *args, **kwargs):
        turno = self.get_object()
        return Response(VenTurnoConDetallesSerializer(turno).data)

    @extend_schema(
        summary='Abrir turno',
        description=(
            'Abre un turno en la caja para el usuario que hace la petición. Una caja y un '
            'cajero tienen a lo sumo un turno abierto.'
        ),
        request=VenTurnoAbrirRequestSerializer,
        responses={201: VenTurnoSerializer},
    )
    @action(detail=False, methods=['post'])
    def abrir(self, request):
        datos = VenTurnoAbrirRequestSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        turno = turno_servicio.abrir(
            caja=datos.validated_data['caja'],
            usuario=request.user,
            base=datos.validated_data['base'],
            cuenta_banco=datos.validated_data.get('cuenta_banco'),
        )
        return Response(VenTurnoSerializer(turno).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Turno abierto del usuario',
        description='El turno abierto de quien hace la petición; 404 si no tiene.',
        responses={200: VenTurnoSerializer},
    )
    @action(detail=False, methods=['get'])
    def abierto(self, request):
        turno = self.get_queryset().filter(usuario=request.user.email, estado_cerrado=False).first()
        if turno is None:
            raise NotFound('No tiene un turno abierto.')
        return Response(VenTurnoSerializer(turno).data)

    @extend_schema(
        summary='Resumen del turno',
        description=(
            'Lo vendido y lo esperado por cuenta bancaria (pagos más la base). Es lo que el '
            'cajero tiene que contar antes de cerrar. En un turno cerrado devuelve lo '
            'guardado al cierre.'
        ),
        responses={200: VenTurnoResumenSerializer},
    )
    @action(detail=True, methods=['get'])
    def resumen(self, request, pk=None):
        turno = self.get_object()
        if turno.estado_cerrado:
            detalles = turno.turnos_detalles_turno_rel.select_related('cuenta_banco').order_by('cuenta_banco__nombre')
            cuentas = [
                {'cuenta_banco': d.cuenta_banco_id, 'cuenta_banco_nombre': d.cuenta_banco.nombre, 'esperado': d.esperado}
                for d in detalles
            ]
            total, cantidad = turno.total_venta, turno.cantidad_documentos
        else:
            esperados = turno_servicio.esperado(turno)
            nombres = dict(GenCuentaBanco.objects.filter(id__in=esperados).values_list('id', 'nombre'))
            cuentas = sorted(
                (
                    {'cuenta_banco': cuenta_id, 'cuenta_banco_nombre': nombres[cuenta_id], 'esperado': valor}
                    for cuenta_id, valor in esperados.items()
                ),
                key=lambda c: c['cuenta_banco_nombre'],
            )
            total, cantidad = turno_servicio.totales(turno)
        return Response(VenTurnoResumenSerializer({
            'total_venta': total, 'cantidad_documentos': cantidad, 'cuentas': cuentas,
        }).data)

    @extend_schema(
        summary='Cerrar turno',
        description=(
            'Guarda el arqueo: lo contado por cuenta bancaria contra lo esperado. Tiene que '
            'traer toda cuenta con algo esperado, y todas las facturas del turno tienen que '
            'estar aprobadas o anuladas.'
        ),
        request=VenTurnoCerrarRequestSerializer,
        responses={200: VenTurnoConDetallesSerializer},
    )
    @action(detail=False, methods=['post'])
    def cerrar(self, request):
        datos = VenTurnoCerrarRequestSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        turno = turno_servicio.cerrar(
            datos.validated_data['id'],
            [(c['cuenta_banco'], c['valor']) for c in datos.validated_data['contados']],
            datos.validated_data.get('comentario'),
        )
        turno = self.get_queryset().get(pk=turno.pk)
        return Response(VenTurnoConDetallesSerializer(turno).data)

    @extend_schema(
        summary='Imprimir cierre de turno',
        description=(
            'El informe de cierre en rollo de 80 mm, como el tiquete POS. Un turno abierto '
            'sale como pre-cierre: lo esperado por cuenta, sin contado ni diferencia.'
        ),
        responses={(200, 'application/pdf'): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=['get'])
    def imprimir(self, request, pk=None):
        contenido, nombre = turno_imprimir.pdf_turno(self.get_object())
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{nombre}"'
        return response
