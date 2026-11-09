from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from contabilidad.models import ConExogena, ConExogenaDetalle, ConExogenaFormato
from contabilidad.serializers import ConExogenaDetalleSerializer
from seguridad.permissions import TienePermisoModelo
from utilidades.mixins import FiltrosDinamicosMixin


@extend_schema(tags=['Exógena detalle'])
class ConExogenaDetalleViewSet(
    FiltrosDinamicosMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Los formatos que la empresa presenta en el año de una exógena.

    Al agregar un formato, si no llega `cuantia_menor` se copia la del formato.
    Después solo se edita la cuantía: cambiar de formato es quitarlo y agregar
    el otro. Nada se modifica si el formato o su exógena están presentados.
    """

    serializer_class = ConExogenaDetalleSerializer
    permission_classes = [TienePermisoModelo]

    def get_queryset(self):
        return ConExogenaDetalle.objects.select_related(
            *ConExogenaDetalleSerializer.select_related_lista
        ).order_by('formato_id')

    def create(self, request, *args, **kwargs):
        exogena_id = request.data.get('exogena')
        formato_id = request.data.get('formato')
        if exogena_id in (None, ''):
            raise ValidationError({'detail': 'El campo exogena es requerido.'})
        if formato_id in (None, ''):
            raise ValidationError({'detail': 'El campo formato es requerido.'})
        try:
            exogena = ConExogena.objects.get(pk=exogena_id)
        except (ConExogena.DoesNotExist, ValueError, TypeError):
            raise ValidationError({'detail': 'La exógena no existe.'})
        try:
            formato = ConExogenaFormato.objects.get(pk=formato_id)
        except (ConExogenaFormato.DoesNotExist, ValueError, TypeError):
            raise ValidationError({'detail': 'El formato no existe.'})
        if exogena.estado_presentado:
            raise ValidationError({'detail': 'La exógena está presentada y no se puede modificar.'})
        if exogena.exogenas_detalles_exogena_rel.filter(formato=formato).exists():
            raise ValidationError({'detail': f'El formato {formato.id} ya está en la exógena {exogena.anio}.'})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if 'cuantia_menor' not in request.data:
            serializer.save(cuantia_menor=formato.cuantia_menor)
        else:
            serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        detalle = self.get_object()
        if detalle.estado_presentado or detalle.exogena.estado_presentado:
            raise ValidationError({'detail': 'El formato está presentado y no se puede modificar.'})
        for campo, actual in (('exogena', detalle.exogena_id), ('formato', detalle.formato_id)):
            valor = request.data.get(campo)
            if valor not in (None, '') and str(valor) != str(actual):
                raise ValidationError({
                    'detail': f'El campo {campo} no se cambia; quita el formato y agrega el correcto.',
                })
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            try:
                detalle = (
                    ConExogenaDetalle.objects.select_for_update()
                    .select_related('exogena').get(pk=kwargs['pk'])
                )
            except ConExogenaDetalle.DoesNotExist:
                raise NotFound('Formato de la exógena no encontrado.')
            if detalle.estado_presentado or detalle.exogena.estado_presentado:
                raise ValidationError({'detail': 'El formato está presentado y no se puede quitar.'})
            detalle.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
