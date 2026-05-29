import importlib

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from general.models import GenModelo
from general.serializers import GenModeloSerializer


# ---- Resolución de tipo de dato (amigable para el front) ----

# Tipos de campo del modelo Django -> tipo expuesto al front.
_TIPOS_MODELO = {
    'AutoField': 'entero',
    'BigAutoField': 'entero',
    'SmallAutoField': 'entero',
    'IntegerField': 'entero',
    'BigIntegerField': 'entero',
    'SmallIntegerField': 'entero',
    'PositiveIntegerField': 'entero',
    'PositiveBigIntegerField': 'entero',
    'PositiveSmallIntegerField': 'entero',
    'FloatField': 'decimal',
    'DecimalField': 'decimal',
    'BooleanField': 'booleano',
    'DateField': 'fecha',
    'DateTimeField': 'fecha_hora',
}


def _tipo_serializer_field(field):
    """Deduce el tipo de dato a partir de un field instanciado de DRF."""
    if isinstance(field, serializers.BooleanField):
        return 'booleano'
    if isinstance(field, serializers.IntegerField):
        return 'entero'
    if isinstance(field, (serializers.FloatField, serializers.DecimalField)):
        return 'decimal'
    if isinstance(field, serializers.DateTimeField):
        return 'fecha_hora'
    if isinstance(field, serializers.DateField):
        return 'fecha'
    if isinstance(field, serializers.RelatedField):
        return 'relacion'
    if isinstance(field, serializers.ChoiceField):
        return 'opcion'
    return 'texto'


def _tipo_modelo_field(model, nombre):
    """Deduce el tipo de dato de un campo/lookup del modelo (acepta sufijo `_id`)."""
    try:
        field = model._meta.get_field(nombre)
    except FieldDoesNotExist:
        if nombre.endswith('_id'):
            try:
                field = model._meta.get_field(nombre[:-3])
            except FieldDoesNotExist:
                return 'texto'
        else:
            return 'texto'
    if field.is_relation:
        return 'relacion'
    return _TIPOS_MODELO.get(field.get_internal_type(), 'texto')


def _etiqueta(nombre):
    return nombre.replace('_', ' ').capitalize()


class _CampoEstructuraSerializer(serializers.Serializer):
    """Solo para documentación del schema."""
    nombre = serializers.CharField()
    etiqueta = serializers.CharField()
    tipo = serializers.CharField()


class _EstructuraSerializer(serializers.Serializer):
    """Solo para documentación del schema."""
    id = serializers.IntegerField()
    modelo = serializers.CharField()
    nombre = serializers.CharField()
    campos_lista = _CampoEstructuraSerializer(many=True)
    campos_filtrables = _CampoEstructuraSerializer(many=True)


@extend_schema(tags=['Modelo'])
class GenModeloViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GenModeloSerializer
    queryset = GenModelo.objects.all().order_by('app', 'nombre')

    @extend_schema(
        summary='Estructura de lista y filtros de un modelo',
        description=(
            'Devuelve los campos de lista y los campos filtrables del modelo, '
            'cada uno con su nombre, etiqueta y tipo de dato. El front lo usa '
            'para renderizar tablas y filtros dinámicos.'
        ),
        responses=_EstructuraSerializer,
    )
    @action(detail=True, methods=['get'])
    def estructura(self, request, pk=None):
        modelo = self.get_object()

        serializer_cls = self._resolver_serializer(modelo)
        if serializer_cls is None:
            return Response(
                {'detail': f'El modelo {modelo.clase} no tiene estructura de lista configurada'},
                status=status.HTTP_404_NOT_FOUND,
            )

        model = apps.get_model(modelo.app, modelo.clase)
        fields = serializer_cls().fields

        # Campos de lista: lo que devuelve el endpoint de lista (orden del serializer).
        campos_lista = [
            {'nombre': nombre, 'etiqueta': str(field.label or _etiqueta(nombre)), 'tipo': _tipo_serializer_field(field)}
            for nombre, field in fields.items()
            if not field.write_only
        ]

        # Campos filtrables: whitelist declarada en el serializer.
        nombres_filtrables = sorted(getattr(serializer_cls, 'campos_filtrables', set()))
        campos_filtrables = []
        for nombre in nombres_filtrables:
            if nombre in fields:
                field = fields[nombre]
                campos_filtrables.append({
                    'nombre': nombre,
                    'etiqueta': str(field.label or _etiqueta(nombre)),
                    'tipo': _tipo_serializer_field(field),
                })
            else:
                campos_filtrables.append({
                    'nombre': nombre,
                    'etiqueta': _etiqueta(nombre),
                    'tipo': _tipo_modelo_field(model, nombre),
                })

        return Response({
            'id': modelo.id,
            'modelo': modelo.clase,
            'nombre': modelo.nombre,
            'campos_lista': campos_lista,
            'campos_filtrables': campos_filtrables,
        })

    @staticmethod
    def _resolver_serializer(modelo):
        """Resuelve `{app}.serializers.{Clase}Serializer` por convención."""
        try:
            module = importlib.import_module(f'{modelo.app}.serializers')
        except ModuleNotFoundError:
            return None
        return getattr(module, f'{modelo.clase}Serializer', None)
