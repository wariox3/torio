from rest_framework import serializers

from general.models import GenDocumentoPago


class GenDocumentoPagoSerializer(serializers.ModelSerializer):
    """
    Solo valida la forma. Ninguna escritura pasa por su `save()`: todas van por
    `servicios.documento_pago`, que es el único que mantiene `GenDocumento.pago`.
    """

    cuenta_banco_nombre = serializers.CharField(source='cuenta_banco.nombre', read_only=True)

    class Meta:
        model = GenDocumentoPago
        fields = [
            'id',
            'documento',
            'cuenta_banco',
            'cuenta_banco_nombre',
            'pago',
            'estado_anulado',
        ]
        read_only_fields = ['id', 'estado_anulado']

    def validate_pago(self, valor):
        if valor <= 0:
            raise serializers.ValidationError('Debe ser mayor que cero.')
        return valor
