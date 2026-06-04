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
