from rest_framework import serializers

from contabilidad.models import ConConciliacion


class ConConciliacionSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'fecha_desde', 'fecha_hasta', 'cuenta_banco'}
    select_related_lista = ('cuenta_banco',)
    ordenamiento_default_lista = ('-id',)

    cuenta_banco_nombre = serializers.CharField(source='cuenta_banco.nombre', read_only=True, default=None)

    class Meta:
        model = ConConciliacion
        fields = ['id', 'fecha_desde', 'fecha_hasta', 'cuenta_banco', 'cuenta_banco_nombre']
        read_only_fields = ['id']


class ConConciliacionSeleccionarSerializer(serializers.ModelSerializer):
    cuenta_banco_nombre = serializers.CharField(source='cuenta_banco.nombre', read_only=True, default=None)

    class Meta:
        model = ConConciliacion
        fields = ['id', 'fecha_desde', 'fecha_hasta', 'cuenta_banco', 'cuenta_banco_nombre']
