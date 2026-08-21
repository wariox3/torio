from rest_framework import serializers

from general.models import GenParametro


class GenParametroSerializer(serializers.ModelSerializer):
    """
    Solo lectura a propósito: `GenParametro` guarda hechos que produce el
    sistema, no datos que el usuario edite. Cada campo lo escribe el flujo que
    lo origina — `gen_factura_electronica_activa` sale de consultar el servicio
    de facturación electrónica, no de que el front lo mande.
    """

    class Meta:
        model = GenParametro
        fields = [
            'id',
            'gen_factura_electronica_activa',
            'gen_factura_electronica_emisor',
            'gen_certificado_vence',
        ]
        read_only_fields = fields
