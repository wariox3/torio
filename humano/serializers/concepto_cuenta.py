from rest_framework import serializers

from humano.models import HumConceptoCuenta


class HumConceptoCuentaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'concepto_id', 'tipo_costo_id', 'cuenta_id'}
    select_related_lista = ('concepto', 'tipo_costo', 'cuenta')
    ordenamiento_default_lista = ('-id',)

    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, default=None)
    tipo_costo_nombre = serializers.CharField(source='tipo_costo.nombre', read_only=True, default=None)
    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, default=None)

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
