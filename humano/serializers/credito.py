from rest_framework import serializers

from humano.models import HumCredito


class HumCreditoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'contrato_id', 'concepto_id', 'inactivo', 'pagado', 'fecha_inicio'}
    select_related_lista = ('concepto', 'contrato', 'contrato__contacto')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, allow_null=True)
    contrato_contacto_numero_identificacion = serializers.CharField(
        source='contrato.contacto.numero_identificacion', read_only=True, allow_null=True,
    )
    concepto_nombre = serializers.CharField(source='concepto.nombre', read_only=True, allow_null=True)

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
            'contrato_contacto_numero_identificacion',
        ]
        read_only_fields = ['id', 'abono', 'saldo', 'cuota_actual', 'pagado']

    # `saldo` es de solo lectura: lo calcula el servidor. Sin esto quedaba en
    # cero y la nómina, que solo toma créditos con saldo, nunca lo descontaba.

    def validate(self, datos):
        total = datos.get('total')
        if self.instance is not None and total is not None and total < self.instance.abono:
            raise serializers.ValidationError({
                'detail': f'El total no puede ser menor a lo ya abonado ({self.instance.abono:,.2f}).',
            })
        return datos

    def create(self, validated_data):
        validated_data['saldo'] = validated_data.get('total', 0)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Lo abonado lo escriben las nóminas: cambiar el total solo mueve lo que falta.
        total = validated_data.get('total', instance.total)
        validated_data['saldo'] = total - instance.abono
        return super().update(instance, validated_data)
