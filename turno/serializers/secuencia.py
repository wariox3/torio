from rest_framework import serializers

from turno.models import TurSecuencia

# Ranuras de turno de la secuencia (cada una guarda el codigo de un TurTurno)
CAMPOS_DIAS = [f'dia_{n}' for n in range(1, 32)]
CAMPOS_SEMANA = [
    'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo',
    'festivo', 'domingo_festivo',
]
CAMPOS_RANURAS = CAMPOS_DIAS + CAMPOS_SEMANA


class TurSecuenciaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'nombre', 'estado_inactivo'}
    ordenamiento_default_lista = ('nombre',)

    class Meta:
        model = TurSecuencia
        fields = [
            'id',
            'nombre',
            *CAMPOS_RANURAS,
            'horas',
            'dias',
            'homologar',
            'estado_inactivo',
        ]
        read_only_fields = ['id']
