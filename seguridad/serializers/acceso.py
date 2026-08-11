from rest_framework import serializers

from seguridad.models import SegAcceso


class SegAccesoSerializer(serializers.ModelSerializer):
    """
    Una entrada del historial de ingresos, para el propio usuario.

    No expone `email` ni `usuario`: la lista ya está filtrada por la cuenta
    autenticada, así que repetirlos solo agregaría datos a una respuesta que puede
    quedar en un log del front.
    """

    resultado_nombre = serializers.CharField(source='get_resultado_display', read_only=True)

    class Meta:
        model = SegAcceso
        fields = [
            'id', 'fecha', 'ip', 'user_agent', 'resultado', 'resultado_nombre',
            'metodo_mfa', 'dispositivo_recordado', 'codigo_respaldo',
        ]
        read_only_fields = fields
