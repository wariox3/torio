from rest_framework import serializers

from turno.models import TurProgramacionSimulacion


class TurProgramacionSimulacionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha', 'turno', 'festivo', 'posicion', 'contrato', 'documento_detalle',
    }
    select_related_lista = (
        'turno',
        'contrato',
        'contrato__contacto',
        'documento_detalle',
    )
    ordenamiento_default_lista = ('fecha', 'id')

    turno_nombre = serializers.CharField(source='turno.nombre', read_only=True, default=None)
    contrato_nombre = serializers.CharField(
        source='contrato.contacto.nombre_corto', read_only=True, default=None,
    )
    contrato_contacto_numero_identificacion = serializers.CharField(
        source='contrato.contacto.numero_identificacion', read_only=True, default=None,
    )

    class Meta:
        model = TurProgramacionSimulacion
        fields = [
            'id',
            'fecha',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
            'festivo',
            'posicion',
            'contrato',
            'contrato_nombre',
            'contrato_contacto_numero_identificacion',
            'documento_detalle',
            'turno',
            'turno_nombre',
        ]
        read_only_fields = ['id']
