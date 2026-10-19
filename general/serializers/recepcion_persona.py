from rest_framework import serializers

from general.models import GenIdentificacion


class RecepcionPersonaSerializer(serializers.Serializer):
    """
    La persona que recibe la factura o la mercancía en los eventos RADIAN 030 y
    032. La guarda `GenConfiguracion.com_recepcion_recibe` como sugerencia y la
    pide `documento-evento`.

    `identificacion` es el id de `GenIdentificacion` de torio, no el código DIAN
    que espera rededoc: la conversión la hace el servicio al enviar el evento.
    """
    identificacion = serializers.IntegerField(min_value=1, help_text='Id de GenIdentificacion.')
    numero_identificacion = serializers.CharField(max_length=20)
    nombres = serializers.CharField(max_length=100)
    apellidos = serializers.CharField(max_length=100)
    cargo = serializers.CharField(max_length=100, required=False, allow_blank=True)
    area = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_identificacion(self, valor):
        if not GenIdentificacion.objects.filter(pk=valor).exists():
            raise serializers.ValidationError('El tipo de identificación no existe.')
        return valor
