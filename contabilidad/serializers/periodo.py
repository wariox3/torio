from rest_framework import serializers

from contabilidad.models import ConPeriodo


class ConPeriodoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'anio', 'mes', 'estado_bloqueado', 'estado_cerrado', 'estado_inconsistencia'}
    ordenamiento_default_lista = ('-anio', '-mes')

    class Meta:
        model = ConPeriodo
        fields = ['id', 'anio', 'mes', 'estado_bloqueado', 'estado_cerrado', 'estado_inconsistencia']
        read_only_fields = ['id']

    def validate(self, attrs):
        # `anio` y `mes` forman el id del periodo, así que cambiarlos en uno que ya
        # existe no es una edición: sería otro periodo, con otra PK.
        if self.instance is not None:
            for campo in ('anio', 'mes'):
                if campo in attrs and attrs[campo] != getattr(self.instance, campo):
                    raise serializers.ValidationError({
                        campo: 'No se puede cambiar el año ni el mes de un periodo existente',
                    })
        return attrs
