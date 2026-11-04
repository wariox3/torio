from rest_framework import serializers

from venta.models import VenCaja


class VenCajaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {'id', 'nombre', 'placa', 'ubicacion', 'tipo', 'estado_activo', 'sede_id'}
    select_related_lista = ('sede',)
    ordenamiento_default_lista = ('nombre',)

    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, allow_null=True)

    class Meta:
        model = VenCaja
        fields = [
            'id',
            'nombre',
            'placa',
            'ubicacion',
            'tipo',
            'estado_activo',
            'sede',
            'sede_nombre',
        ]
        read_only_fields = ['id']
