from rest_framework import serializers

from humano.models import HumConceptoCuenta


class HumConceptoCuentaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'concepto_id', 'tipo_costo_id', 'cuenta_id'}
    select_related_lista = ('concepto', 'tipo_costo', 'cuenta')
    ordenamiento_default_lista = ('-id',)

    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, allow_null=True)
    tipo_costo_nombre = serializers.CharField(source='tipo_costo.nombre', read_only=True, allow_null=True)
    cuenta_codigo = serializers.CharField(source='cuenta.codigo', read_only=True, allow_null=True)
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
            'cuenta_codigo',
            'cuenta_nombre',
        ]
        read_only_fields = ['id']
        # La unicidad la revisa `validate` con su propio mensaje; sin esto DRF
        # deduciría de la restricción del modelo otro validador con uno genérico.
        validators = []

    def validate_cuenta(self, cuenta):
        # Las cuentas de agrupación (clase, grupo, mayor) no reciben movimiento.
        if not cuenta.permite_movimiento:
            raise serializers.ValidationError(f'La cuenta {cuenta.codigo} no permite movimientos.')
        return cuenta

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


class HumConceptoCuentaActualizarSerializer(HumConceptoCuentaSerializer):
    """
    Edición: solo se cambia la cuenta. El concepto y el tipo de costo son lo que
    identifica la fila; si están mal, se elimina y se crea otra.
    """

    class Meta(HumConceptoCuentaSerializer.Meta):
        read_only_fields = ['id', 'concepto', 'tipo_costo']
