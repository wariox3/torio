from rest_framework import serializers

from humano.models import HumConceptoCuenta


class HumConceptoCuentaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'concepto_id', 'tipo_costo_id', 'cuenta_id'}
    select_related_lista = ('concepto', 'tipo_costo', 'cuenta')
    ordenamiento_default_lista = ('-id',)

    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, allow_null=True)
    tipo_costo_nombre = serializers.CharField(source='tipo_costo.nombre', read_only=True, allow_null=True)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, allow_null=True)

    class Meta:
        model = HumConceptoCuenta
        fields = [
            'id',
            'concepto',
            'concepto_nombre',
            'tipo_costo',
            'tipo_costo_nombre',
            'cuenta',
            'cuenta_nombre',
        ]
        read_only_fields = ['id']
        # La unicidad la revisa `validate` con su propio mensaje; sin esto DRF
        # deduciría de la restricción del modelo otro validador con uno genérico.
        validators = []

    def validate(self, datos):
        concepto = datos.get('concepto', getattr(self.instance, 'concepto', None))
        tipo_costo = datos.get('tipo_costo', getattr(self.instance, 'tipo_costo', None))
        repetido = HumConceptoCuenta.objects.filter(concepto=concepto, tipo_costo=tipo_costo)
        if self.instance is not None:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise serializers.ValidationError(
                f'El concepto {concepto.nombre} ya tiene cuenta para el tipo de costo {tipo_costo.nombre}.'
            )
        return datos
