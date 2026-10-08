from rest_framework import serializers

from general.models import GenParametro


class GenParametroSerializer(serializers.ModelSerializer):
    """
    Solo lectura a propósito: `GenParametro` guarda hechos que produce el
    sistema, no datos que el usuario edite. Cada campo lo escribe el flujo que
    lo origina — `gen_asistente_electronico` lo apaga el endpoint que termina el
    asistente de facturación electrónica, no un PATCH del front.
    """

    class Meta:
        model = GenParametro
        fields = [
            'id',
            'gen_asistente_electronico',
            'gen_rededoc_emisor',
            'gen_certificado_vence',
            'gen_electronico_habilitado_facturacion',
            'gen_electronico_habilitado_nomina',
            'gen_electronico_habilitado_equivalente',
            'gen_asistente_datos_iniciales',
        ]
        read_only_fields = fields
