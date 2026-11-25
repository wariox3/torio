from django.db import transaction
from rest_framework import serializers

from contabilidad.models import ConCuenta, ConMovimiento
from contabilidad.servicios import cuenta as reglas

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
        # Nivel y catálogos se derivan del código (`contabilidad.servicios.cuenta`):
        # lo que mande el front para ellos se ignora.
        read_only_fields = [
            'id', 'nivel', 'cuenta_clase', 'cuenta_grupo', 'cuenta_cuenta', 'cuenta_subcuenta',
        ]

    def validate(self, attrs):
        cuenta = self.instance
        self._padre = None

        cambia_codigo = 'codigo' in attrs and (cuenta is None or attrs['codigo'] != cuenta.codigo)
        if cambia_codigo:
            if cuenta is not None:
                if ConMovimiento.objects.filter(cuenta_id=cuenta.pk).exists():
                    raise serializers.ValidationError({
                        'detail': f'La cuenta {cuenta.codigo} ya tiene movimientos y no se puede cambiar su código.',
                    })
                if reglas.tiene_hijas(cuenta):
                    raise serializers.ValidationError({
                        'detail': f'La cuenta {cuenta.codigo} tiene auxiliares y no se puede cambiar su código.',
                    })
            attrs.update(self._estructura(reglas.normalizar_codigo(attrs['codigo'])))

        # Activarlo con hijas rompería "solo las hojas mueven". Solo el cambio: una
        # cuenta que ya venía así (datos viejos) se puede seguir editando.
        if (
            cuenta is not None
            and attrs.get('permite_movimiento')
            and not cuenta.permite_movimiento
            and reglas.tiene_hijas(cuenta)
        ):
            raise serializers.ValidationError({
                'detail': f'La cuenta {cuenta.codigo} tiene auxiliares: solo ellas pueden permitir movimiento.',
            })

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

    def _estructura(self, codigo):
        """Valida el código contra el PUC y su padre; devuelve los campos derivados."""
        try:
            reglas.validar_formato(codigo)
            datos = {'codigo': codigo, **reglas.derivar(codigo, reglas.cargar_catalogos([codigo]))}
            codigo_padre = reglas.codigo_padre(codigo)
            if codigo_padre:
                padre = ConCuenta.objects.filter(codigo=codigo_padre).first()
                if padre is None:
                    raise reglas.CuentaInvalida(reglas.mensaje_padre_inexistente(codigo))
                padre_usos = reglas.usos([padre.pk]).get(padre.pk, []) if padre.permite_movimiento else []
                reglas.validar_padre(padre, codigo, padre_usos)
                self._padre = padre
        except reglas.CuentaInvalida as e:
            raise serializers.ValidationError({'detail': str(e)}) from e
        return datos

    def create(self, validated_data):
        with transaction.atomic():
            cuenta = super().create(validated_data)
            if self._padre is not None:
                reglas.apagar_movimiento([self._padre.pk])
        return cuenta

    def update(self, instance, validated_data):
        with transaction.atomic():
            cuenta = super().update(instance, validated_data)
            if self._padre is not None:
                reglas.apagar_movimiento([self._padre.pk])
        return cuenta
