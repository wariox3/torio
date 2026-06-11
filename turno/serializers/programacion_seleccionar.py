from rest_framework import serializers

from turno.models import TurProgramacion


class TurProgramacionSeleccionarSerializer(serializers.ModelSerializer):
    contrato_nombre = serializers.CharField(
        source='contrato.contacto.nombre_corto', read_only=True, default=None,
    )
    turno_nombre = serializers.CharField(source='turno.nombre', read_only=True, default=None)

    class Meta:
        model = TurProgramacion
        fields = ['id', 'fecha', 'contrato', 'contrato_nombre', 'turno', 'turno_nombre']
