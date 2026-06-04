from rest_framework import serializers

from humano.models import HumCredito


class HumCreditoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato', 'concepto', 'inactivo', 'pagado', 'fecha_inicio'}
    select_related_lista = ('concepto', 'contrato', 'contrato__contacto')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)
    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, default=None)

    class Meta:
        model = HumCredito
        fields = [
            'id',
            'fecha_inicio',
            'total',
            'cuota',
            'abono',
            'saldo',
            'cantidad_cuotas',
            'cuota_actual',
            'validar_cuotas',
            'inactivo',
            'pagado',
            'aplica_prima',
            'aplica_cesantia',
            'comentario',
            'concepto',
            'concepto_nombre',
            'contrato',
            'contrato_nombre',
        ]
        read_only_fields = ['id', 'abono', 'saldo', 'cuota_actual', 'pagado']
