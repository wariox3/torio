from django.db import transaction
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from contabilidad.models import ConExogena, ConExogenaDetalle, ConExogenaFormato
from contabilidad.serializers import ConExogenaDetalleSerializer, ConExogenaSerializer
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Exógena'])
class ConExogenaViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    La información exógena de un año gravable. Sus formatos se administran en
    `exogena-detalle/`, o todos de una vez con `cargar-formatos/`.

    El año no se edita: con formatos generados, cambiarlo dejaría los datos de
    otro año. Presentada, la exógena no se modifica ni se borra.
    """

    serializer_class = ConExogenaSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        return ConExogena.objects.order_by('-anio')

    def create(self, request, *args, **kwargs):
        anio = request.data.get('anio')
        # Un año que no es número lo rechaza el serializer; acá solo se revisa
        # que el año no esté repetido.
        if str(anio or '').strip().isdigit() and ConExogena.objects.filter(anio=int(anio)).exists():
            raise ValidationError({'detail': f'Ya existe la exógena del año {anio}.'})
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        exogena = self.get_object()
        if exogena.estado_presentado:
            raise ValidationError({'detail': 'La exógena está presentada y no se puede modificar.'})
        anio = request.data.get('anio')
        if anio not in (None, '') and str(anio) != str(exogena.anio):
            raise ValidationError({
                'detail': 'El año de la exógena no se cambia; elimínala y créala con el año correcto.',
            })
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            try:
                exogena = ConExogena.objects.select_for_update().get(pk=kwargs['pk'])
            except ConExogena.DoesNotExist:
                raise NotFound('Exógena no encontrada.')
            detalles = exogena.exogenas_detalles_exogena_rel.all()
            if exogena.estado_presentado or detalles.filter(estado_presentado=True).exists():
                raise ValidationError({'detail': 'La exógena tiene formatos presentados y no se puede eliminar.'})
            detalles.delete()
            exogena.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary='Cargar todos los formatos',
        description=(
            'Agrega a la exógena todos los formatos del catálogo que todavía no tiene, '
            'cada uno con la cuantía menor del formato. Los que ya estaban no se tocan, '
            'así que sirve también para recuperar uno que se quitó. Devuelve todos los '
            'formatos de la exógena.'
        ),
        request=None,
        responses=inline_serializer('ConExogenaCargarFormatosRespuesta', {
            'creados': serializers.IntegerField(),
            'detalles': ConExogenaDetalleSerializer(many=True),
        }),
    )
    @action(detail=True, methods=['post'], url_path='cargar-formatos')
    def cargar_formatos(self, request, pk=None):
        with transaction.atomic():
            try:
                exogena = ConExogena.objects.select_for_update().get(pk=pk)
            except ConExogena.DoesNotExist:
                raise NotFound('Exógena no encontrada.')
            if exogena.estado_presentado:
                raise ValidationError({'detail': 'La exógena está presentada y no se puede modificar.'})

            existentes = set(
                exogena.exogenas_detalles_exogena_rel.values_list('formato_id', flat=True)
            )
            nuevos = [
                ConExogenaDetalle(exogena=exogena, formato=formato, cuantia_menor=formato.cuantia_menor)
                for formato in ConExogenaFormato.objects.exclude(id__in=existentes)
            ]
            ConExogenaDetalle.objects.bulk_create(nuevos)

        detalles = exogena.exogenas_detalles_exogena_rel.select_related('formato').order_by('formato_id')
        return Response({
            'creados': len(nuevos),
            'detalles': ConExogenaDetalleSerializer(detalles, many=True).data,
        })
