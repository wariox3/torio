from rest_framework import serializers

from general.models import GenFormaPago


class GenFormaPagoSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {'id', 'nombre'}
    select_related_lista = ('cuenta',)
    ordenamiento_default_lista = ('id',)

    cuenta_nombre = serializers.CharField(source='cuenta.nombre', read_only=True, default=None)

    class Meta:
        model = GenFormaPago
        fields = ['id', 'nombre', 'cuenta', 'cuenta_nombre']
        read_only_fields = ['id']
