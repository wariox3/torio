from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from general.models import GenDocumentoDetalle
from humano.formatos import FormatoVacacion
from humano.models import HumNovedad
from humano.serializers import (
    HumNovedadExportarSerializer,
    HumNovedadImportarSerializer,
    HumNovedadSeleccionarSerializer,
    HumNovedadSerializer,
)
from humano.servicios import novedad as servicio_novedad
from humano.servicios import VacacionError, aprobar_vacacion, interrumpir_vacacion, recalcular_periodos
from humano.servicios.nomina import NOVEDAD_TIPO_VACACION
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import (
    ExportarExcelMixin,
    FiltrosDinamicosMixin,
    ImportarExcelMixin,
)
from utilidades.paginacion import SeleccionarPaginacion

_LIST_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
]

_SELECCIONAR_PARAMS = [
    OpenApiParameter('search', str, description='Buscar por empleado'),
    OpenApiParameter('contrato_id', int, description='Solo las novedades de este contrato'),
    OpenApiParameter('novedad_tipo_id', int, description='Solo las novedades de este tipo'),
]


@extend_schema(tags=['Novedad'])
class HumNovedadViewSet(
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
    serializer_class = HumNovedadSerializer
    serializer_class_exportar = HumNovedadExportarSerializer
    serializer_class_importar = HumNovedadImportarSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        qs = HumNovedad.objects.select_related(
            *HumNovedadSerializer.select_related_lista
        ).order_by('-id')

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)

        return qs

    def _guardar_y_liquidar(self, serializer, antes=None):
        # Una novedad que no se puede liquidar no se guarda: pagaría cero.
        with transaction.atomic():
            novedad = serializer.save()
            try:
                servicio_novedad.liquidar(novedad)
            except servicio_novedad.NovedadError as e:
                raise ValidationError({'detail': e.detail})
            # Si es (o era) vacación, se reencadenan los periodos de su contrato, y
            # del anterior si cambió de contrato o dejó de ser vacación.
            contratos = set()
            if novedad.novedad_tipo_id == NOVEDAD_TIPO_VACACION:
                contratos.add(novedad.contrato_id)
            if antes and antes[1] == NOVEDAD_TIPO_VACACION:
                contratos.add(antes[0])
            recalcular_periodos(contratos)

    def perform_create(self, serializer):
        self._guardar_y_liquidar(serializer)

    def perform_update(self, serializer):
        instancia = serializer.instance
        self._guardar_y_liquidar(serializer, antes=(instancia.contrato_id, instancia.novedad_tipo_id))

    def perform_destroy(self, instance):
        if instance.estado_aprobado:
            raise ValidationError({'detail': 'La novedad está aprobada: no se puede eliminar.'})
        # Las dos FK que apuntan a la novedad son PROTECT; se revisan antes para
        # decir qué la está usando y cómo liberarla.
        linea = (
            GenDocumentoDetalle.objects.filter(novedad=instance)
            .select_related('documento__documento_tipo').order_by('id').first()
        )
        if linea is not None:
            documento = linea.documento
            nombre = ' '.join(
                str(parte) for parte in (documento.documento_tipo.nombre, documento.numero) if parte is not None
            )
            paso = 'desapruebe y desgenere' if documento.estado_aprobado else 'desgenere'
            raise ValidationError({'detail': (
                f'La novedad está en el documento {documento.pk} ({nombre}); '
                f'{paso} la programación antes de eliminarla.'
            )})
        if HumNovedad.objects.filter(novedad_referencia=instance).exists():
            raise ValidationError({'detail': 'La novedad tiene prórrogas; elimínelas primero.'})
        with transaction.atomic():
            instance.delete()
            if instance.novedad_tipo_id == NOVEDAD_TIPO_VACACION:
                recalcular_periodos({instance.contrato_id})

    @extend_schema(
        request=inline_serializer('NovedadLiquidarRequest', {'id': serializers.IntegerField()}),
        responses=HumNovedadSerializer,
    )
    @action(detail=False, methods=['post'], url_path='liquidar')
    def liquidar(self, request):
        """Vuelve a liquidar una novedad, p. ej. después de cambiar el salario del contrato."""
        novedad_id = request.data.get('id')
        if not novedad_id:
            return Response({'detail': 'El campo id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            novedad = self.get_queryset().get(pk=novedad_id)
        except (HumNovedad.DoesNotExist, ValueError, TypeError):
            raise NotFound('Novedad no encontrada.')
        if novedad.estado_aprobado:
            return Response({'detail': 'La novedad está aprobada: no se puede volver a liquidar.'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            servicio_novedad.liquidar(novedad)
        except servicio_novedad.NovedadError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(HumNovedadSerializer(novedad).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=inline_serializer('NovedadAprobarRequest', {'id': serializers.IntegerField()}),
        responses=HumNovedadSerializer,
    )
    @action(detail=False, methods=['post'], url_path='aprobar')
    def aprobar(self, request):
        """
        Aprueba una vacación: queda fija (no se edita, borra ni reliquida) y la
        `fecha_ultimo_pago_vacacion` del contrato pasa al fin de su periodo. Solo
        la primera vacación pendiente del contrato.
        """
        novedad_id = request.data.get('id')
        if not novedad_id:
            return Response({'detail': 'El campo id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            novedad = HumNovedad.objects.get(pk=novedad_id)
        except (HumNovedad.DoesNotExist, ValueError, TypeError):
            raise NotFound('Novedad no encontrada.')
        try:
            aprobar_vacacion(novedad)
        except VacacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        novedad = self.get_queryset().get(pk=novedad.pk)
        return Response(HumNovedadSerializer(novedad).data, status=status.HTTP_200_OK)

    @extend_schema(
        request=inline_serializer('NovedadInterrumpirRequest', {
            'id': serializers.IntegerField(),
            'fecha_desde': serializers.DateField(),
            'fecha_hasta': serializers.DateField(help_text='Último día disfrutado antes de la incapacidad.'),
            'dias_disfrutados': serializers.DecimalField(
                max_digits=10, decimal_places=3, help_text='Días hábiles disfrutados.',
            ),
            'dias_disfrutados_reales': serializers.DecimalField(
                max_digits=10, decimal_places=3, help_text='Días calendario disfrutados.',
            ),
        }),
        responses=inline_serializer('NovedadInterrumpirResponse', {
            'novedad': HumNovedadSerializer(),
            'dias_disfrutados_pendientes': serializers.DecimalField(max_digits=10, decimal_places=3),
        }),
    )
    @action(detail=False, methods=['post'], url_path='interrumpir-vacacion')
    def interrumpir(self, request):
        """
        Deja una vacación interrumpida por una incapacidad con las fechas y los días
        que alcanzó a disfrutar, aunque esté aprobada (si es la última aprobada del
        contrato). Una vacación con días en dinero no se interrumpe. Después se
        registra la incapacidad y, cuando el empleado vuelve, la reanudación con
        los días pendientes que devuelve.
        """
        novedad_id = request.data.get('id')
        if not novedad_id:
            return Response({'detail': 'El campo id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        valores = {}
        for campo in ('fecha_desde', 'fecha_hasta'):
            try:
                valores[campo] = serializers.DateField().run_validation(request.data.get(campo))
            except serializers.ValidationError:
                return Response({'detail': f'{campo} es requerida y debe tener formato AAAA-MM-DD.'},
                                status=status.HTTP_400_BAD_REQUEST)
        for campo in ('dias_disfrutados', 'dias_disfrutados_reales'):
            try:
                valores[campo] = serializers.DecimalField(max_digits=10, decimal_places=3).run_validation(
                    request.data.get(campo),
                )
            except serializers.ValidationError:
                return Response({'detail': f'{campo} es requerido y debe ser un número.'},
                                status=status.HTTP_400_BAD_REQUEST)
        try:
            novedad = HumNovedad.objects.get(pk=novedad_id)
        except (HumNovedad.DoesNotExist, ValueError, TypeError):
            raise NotFound('Novedad no encontrada.')
        try:
            novedad, pendientes_disfrute = interrumpir_vacacion(novedad, **valores)
        except VacacionError as e:
            return Response({'detail': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        novedad = self.get_queryset().get(pk=novedad.pk)
        return Response({
            'novedad': HumNovedadSerializer(novedad).data,
            'dias_disfrutados_pendientes': pendientes_disfrute,
        }, status=status.HTTP_200_OK)

    @extend_schema(
        request=inline_serializer('NovedadImprimirRequest', {'id': serializers.IntegerField()}),
        responses={(200, 'application/pdf'): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['post'], url_path='imprimir')
    def imprimir(self, request):
        """La vacación en PDF, aprobada o no, con las firmas del empleado y la empresa."""
        novedad_id = request.data.get('id')
        if not novedad_id:
            return Response({'detail': 'El campo id es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            novedad = HumNovedad.objects.select_related(
                'contrato__contacto', 'contrato__cargo', 'contrato__grupo',
            ).get(pk=novedad_id)
        except (HumNovedad.DoesNotExist, ValueError, TypeError):
            raise NotFound('Novedad no encontrada.')
        if novedad.novedad_tipo_id != NOVEDAD_TIPO_VACACION:
            return Response({'detail': 'Solo las novedades de vacaciones tienen formato.'},
                            status=status.HTTP_400_BAD_REQUEST)

        contenido, nombre = FormatoVacacion(novedad).pdf()
        response = HttpResponse(contenido, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{nombre}"'
        return response

    @extend_schema(parameters=_LIST_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(parameters=_SELECCIONAR_PARAMS, responses=HumNovedadSeleccionarSerializer(many=True))
    @action(detail=False, methods=['get'], pagination_class=SeleccionarPaginacion)
    def seleccionar(self, request):
        qs = HumNovedad.objects.select_related('contrato__contacto', 'novedad_tipo').order_by('-id')
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(contrato__contacto__nombre_corto__icontains=search)
        for campo in ('contrato_id', 'novedad_tipo_id'):
            valor = request.query_params.get(campo, '').strip()
            if valor:
                if not valor.isdigit():
                    raise ValidationError({'detail': f'{campo} debe ser un número.'})
                qs = qs.filter(**{campo: int(valor)})
        pagina = self.paginate_queryset(qs)
        serializer = HumNovedadSeleccionarSerializer(pagina, many=True)
        return self.get_paginated_response(serializer.data)
