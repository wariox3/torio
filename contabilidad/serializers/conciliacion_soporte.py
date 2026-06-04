from rest_framework import serializers

from contabilidad.models import ConConciliacionSoporte


class ConConciliacionSoporteSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'conciliacion', 'estado_conciliado'}
    select_related_lista = ('conciliacion',)
    ordenamiento_default_lista = ('-id',)

    class Meta:
        model = ConConciliacionSoporte
        fields = [
            'id',
            'fecha',
            'debito',
            'credito',
            'detalle',
            'estado_conciliado',
            'conciliacion',
        ]
        read_only_fields = ['id']
