from rest_framework import serializers

from turno.models import TurProgramacion


class TurProgramacionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha', 'contrato', 'documento_detalle', 'turno', 'festivo',
    }
    select_related_lista = (
        'contrato',
        'contrato__contacto',
        'documento_detalle',
        'documento_detalle__puesto',
        'turno',
    )
    ordenamiento_default_lista = ('fecha', 'id')

    contrato_nombre = serializers.CharField(
        source='contrato.contacto.nombre_corto', read_only=True, default=None,
    )
    puesto_nombre = serializers.CharField(
        source='documento_detalle.puesto.nombre', read_only=True, default=None,
    )
    turno_nombre = serializers.CharField(source='turno.nombre', read_only=True, default=None)

    class Meta:
        model = TurProgramacion
        fields = [
            'id',
            'fecha',
            'horas',
            'horas_diurnas',
            'horas_nocturnas',
            'festivo',
            'contrato',
            'contrato_nombre',
            'documento_detalle',
            'puesto_nombre',
            'turno',
            'turno_nombre',
        ]
        read_only_fields = ['id']
