from rest_framework import serializers

from turno.models import TurSecuencia, TurTurno

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

    def validate(self, attrs):
        # Las ranuras guardan códigos de TurTurno; todos los digitados deben existir.
        codigos_por_campo = {
            campo: attrs[campo].strip()
            for campo in CAMPOS_RANURAS
            if attrs.get(campo) and attrs[campo].strip()
        }
        if codigos_por_campo:
            existentes = set(
                TurTurno.objects
                .filter(codigo__in=set(codigos_por_campo.values()))
                .values_list('codigo', flat=True)
            )
            errores = [
                {'campo': campo, 'codigo': codigo,
                 'mensaje': f'El turno "{codigo}" no existe.'}
                for campo, codigo in codigos_por_campo.items()
                if codigo not in existentes
            ]
            if errores:
                raise serializers.ValidationError({
                    'detail': 'Uno o más turnos digitados no existen.',
                    'errores': errores,
                })
        return attrs
