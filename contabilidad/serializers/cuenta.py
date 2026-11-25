from rest_framework import serializers

from contabilidad.models import ConCuenta, ConMovimiento

# Lo que decide cómo se arma un movimiento contra la cuenta. Cambiarlo con
# movimientos ya registrados los deja inconsistentes de golpe: activar una
# exigencia marca como faltante a los que no traen el dato, y desactivarla, como
# sobrante a los que sí.
CARACTERISTICAS = {
    'exige_base': 'exige base',
    'exige_contacto': 'exige contacto',
    'exige_centro_costo': 'exige centro de costo',
    'permite_movimiento': 'permite movimiento',
}


class ConCuentaSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin y ExportarExcelMixin
    campos_filtrables = {
        'id', 'codigo', 'nombre', 'nivel',
        'exige_base', 'exige_contacto', 'exige_centro_costo', 'permite_movimiento',
        'cuenta_clase_id', 'cuenta_grupo_id', 'cuenta_cuenta_id', 'cuenta_subcuenta_id',
    }
    select_related_lista = (
        'cuenta_clase', 'cuenta_grupo', 'cuenta_cuenta', 'cuenta_subcuenta',
    )
    ordenamiento_default_lista = ('codigo',)

    cuenta_clase_nombre = serializers.CharField(source='cuenta_clase.nombre', read_only=True)
    cuenta_grupo_nombre = serializers.CharField(source='cuenta_grupo.nombre', read_only=True)
    cuenta_cuenta_nombre = serializers.CharField(source='cuenta_cuenta.nombre', read_only=True)
    cuenta_subcuenta_nombre = serializers.CharField(source='cuenta_subcuenta.nombre', read_only=True)

    class Meta:
        model = ConCuenta
        fields = [
            'id',
            'codigo',
            'nombre',
            'exige_base',
            'exige_contacto',
            'exige_centro_costo',
            'permite_movimiento',
            'nivel',
            'cuenta_clase',
            'cuenta_clase_nombre',
            'cuenta_grupo',
            'cuenta_grupo_nombre',
            'cuenta_cuenta',
            'cuenta_cuenta_nombre',
            'cuenta_subcuenta',
            'cuenta_subcuenta_nombre',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        cuenta = self.instance
        if cuenta is None:
            return attrs
        # Solo cuenta el cambio real: un PUT que reenvía el mismo valor pasa.
        cambios = [
            etiqueta for campo, etiqueta in CARACTERISTICAS.items()
            if campo in attrs and attrs[campo] != getattr(cuenta, campo)
        ]
        if cambios and ConMovimiento.objects.filter(cuenta_id=cuenta.pk).exists():
            raise serializers.ValidationError({
                'detail': (
                    f'La cuenta {cuenta.codigo} ya tiene movimientos y no se puede '
                    f'cambiar: {", ".join(cambios)}.'
                ),
            })
        return attrs
