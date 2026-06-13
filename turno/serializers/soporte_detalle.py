from rest_framework import serializers

from turno.models import TurSoporteDetalle


class TurSoporteDetalleSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'soporte', 'contrato'}
    select_related_lista = ('soporte', 'contrato', 'contrato__contacto')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(
        source='contrato.contacto.nombre_corto', read_only=True, default=None)

    class Meta:
        model = TurSoporteDetalle
        fields = [
            'id',
            'horas',
            'horas_descansos',
            'horas_diurnas',
            'horas_nocturnas',
            'horas_festivas_diurnas',
            'horas_festivas_nocturnas',
            'horas_extras_diurnas',
            'horas_extras_nocturnas',
            'horas_extras_festivas_diurnas',
            'horas_extras_festivas_nocturnas',
            'horas_recargos_nocturnos',
            'horas_recargos_festivos_diurnos',
            'horas_recargos_festivos_nocturnos',
            'soporte',
            'contrato',
            'contrato_nombre',
        ]
        read_only_fields = ['id']
