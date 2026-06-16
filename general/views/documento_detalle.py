from django.db import transaction
from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumento, GenDocumentoDetalle, GenModalidad, GenSector
from general.serializers import (
    GenDocumentoDetallePendienteSerializer,
    GenDocumentoDetalleSerializer,
)
from general.servicios import LiquidadorSupervigilancia, crear_detalle, sincronizar_impuestos
from utilidades.filtros import aplicar_filtros, aplicar_ordenamientos
from utilidades.mixins import FiltrosDinamicosMixin
from utilidades.mixins.filtros import BusquedaRequest


class CalcularPrecioSupervigilanciaRequestSerializer(serializers.Serializer):
    salario = serializers.DecimalField(max_digits=20, decimal_places=2)
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

    def _bloquear_documento(self, documento_id):
        """Bloquea un documento por su PK (FOR UPDATE) y valida que sea modificable."""
        try:
            documento = GenDocumento.objects.select_for_update().get(pk=documento_id)
        except GenDocumento.DoesNotExist:
            raise NotFound('Documento no encontrado.')
        if not documento.es_mutable():
            raise ValidationError('El documento no es modificable.')
        return documento

    def _bloquear_documento_de_detalle(self, detalle_id):
        """Bloquea el documento dueño de un detalle y valida que sea modificable."""
        try:
            detalle = GenDocumentoDetalle.objects.get(pk=detalle_id)
        except GenDocumentoDetalle.DoesNotExist:
            raise NotFound('Detalle no encontrado.')
        return self._bloquear_documento(detalle.documento_id)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)
        documento_payload = datos.pop('documento', None)
        if documento_payload is None:
            raise ValidationError({'documento': 'Este campo es requerido.'})

        with transaction.atomic():
            documento = self._bloquear_documento(documento_payload.pk)
            detalle = crear_detalle(documento, datos)
            documento.recalcular_totales()
            documento.save()

        return Response(self.get_serializer(detalle).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        with transaction.atomic():
            documento = self._bloquear_documento_de_detalle(kwargs['pk'])
            detalle = documento.documentos_detalles_documento_rel.get(pk=kwargs['pk'])

            serializer = self.get_serializer(detalle, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            datos = dict(serializer.validated_data)
            impuestos = datos.pop('impuestos_ids', None)
            for campo, valor in datos.items():
                setattr(detalle, campo, valor)
            if impuestos is not None:
                sincronizar_impuestos(detalle, impuestos)
            detalle.calcular()
            detalle.save()
            documento.recalcular_totales()
            documento.save()

        return Response(self.get_serializer(detalle).data)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            documento = self._bloquear_documento_de_detalle(kwargs['pk'])
            documento.documentos_detalles_documento_rel.filter(pk=kwargs['pk']).delete()
            documento.recalcular_totales()
            documento.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='masivo')
    def masivo(self, request):
        """Crea varios detalles a la vez sobre un documento existente."""
        documento_id = request.data.get('documento')
        if documento_id is None:
            raise ValidationError({'documento': 'Este campo es requerido.'})

        serializer = self.get_serializer(data=request.data.get('detalles', []), many=True)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise ValidationError({'detalles': 'Debe enviar al menos un detalle.'})

        with transaction.atomic():
            documento = self._bloquear_documento(documento_id)
            detalles = [crear_detalle(documento, datos) for datos in serializer.validated_data]
            documento.recalcular_totales()
            documento.save()

        return Response(
            self.get_serializer(detalles, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=BusquedaRequest)
    @action(detail=False, methods=['post'], url_path='pendiente')
    def pendiente(self, request):
        """
        Lista detalles con saldo pendiente (> 0) usando un serializer liviano.

        La invariante `pendiente > 0` la garantiza el servidor: el cliente solo
        puede *agregar* filtros/ordenamientos (whitelist del serializer liviano),
        nunca quitarla.
        """
        serializer_cls = GenDocumentoDetallePendienteSerializer
        ordenamientos = request.data.get('ordenamientos') or []

        qs = GenDocumentoDetalle.objects.filter(pendiente__gt=0).select_related(
            *serializer_cls.select_related_lista
        )
        qs = aplicar_filtros(qs, request.data.get('filtros') or [], serializer_cls.campos_filtrables)
        qs = aplicar_ordenamientos(qs, ordenamientos, serializer_cls.campos_filtrables)
        if not ordenamientos:
            qs = qs.order_by(*serializer_cls.ordenamiento_default_lista)

        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(serializer_cls(pagina, many=True).data)

    @action(detail=False, methods=['post'], url_path='regenerar-afectado')
    def regenerar_afectado(self, request):
        """Recalcula afectado y pendiente de todos los detalles a partir de sus afectaciones."""
        with transaction.atomic():
            afectaciones = dict(
                GenDocumentoDetalle.objects
                .filter(documento_detalle_afectado__isnull=False)
                .values_list('documento_detalle_afectado_id')
                .annotate(total=Sum('total'))
            )

            detalles = list(GenDocumentoDetalle.objects.all())
            for detalle in detalles:
                detalle.afectado = afectaciones.get(detalle.pk, 0)
                detalle.pendiente = detalle.total - detalle.afectado

            GenDocumentoDetalle.objects.bulk_update(detalles, ['afectado', 'pendiente'])

        return Response({'actualizados': len(detalles)}, status=status.HTTP_200_OK)

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
            salario=datos['salario'],
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
