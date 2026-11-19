from rest_framework import serializers

from general.models import GenUsuarioConfiguracion


class GenUsuarioConfiguracionSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source='sede.nombre', read_only=True, allow_null=True)
    almacen_nombre = serializers.CharField(source='almacen.nombre', read_only=True, allow_null=True)
    caja_nombre = serializers.CharField(source='caja.nombre', read_only=True, allow_null=True)

    class Meta:
        model = GenUsuarioConfiguracion
        fields = [
            'sede',
            'sede_nombre',
            'almacen',
            'almacen_nombre',
            'caja',
            'caja_nombre',
        ]

    def validate_caja(self, caja):
        if caja is not None and not caja.estado_activo:
            raise serializers.ValidationError('La caja está inactiva.')
        return caja

    def validate(self, datos):
        """La caja por defecto tiene que ser de la sede por defecto, si hay sede."""
        sede = datos.get('sede', getattr(self.instance, 'sede', None))
        caja = datos.get('caja', getattr(self.instance, 'caja', None))
        if sede is not None and caja is not None and caja.sede_id != sede.id:
            raise serializers.ValidationError({'caja': 'La caja no pertenece a la sede seleccionada.'})
        return datos
