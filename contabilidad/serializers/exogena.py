from rest_framework import serializers

from contabilidad.models import ConExogena


class ConExogenaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'anio', 'estado_generado', 'estado_presentado'}
    ordenamiento_default_lista = ('-anio',)

    class Meta:
        model = ConExogena
        fields = ['id', 'anio', 'comentario', 'estado_generado', 'estado_presentado']
        read_only_fields = ['id', 'estado_generado', 'estado_presentado']
        # La unicidad del año la revisa la vista, con un mensaje propio.
        extra_kwargs = {'anio': {'validators': []}}
