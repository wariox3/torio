from rest_framework import serializers

from contenedor.models import CtnEventoPago


class CtnEventoPagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CtnEventoPago
        fields = [
            'id', 'fecha', 'evento', 'entorno', 'transaccion',
            'metodo_pago', 'referencia', 'correo', 'estado', 'fecha_transaccion',
            'estado_aplicado', 'vr_original', 'datos',
        ]
        read_only_fields = ['id', 'fecha']
