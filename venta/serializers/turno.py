from rest_framework import serializers

from general.models import GenCuentaBanco
from venta.models import VenCaja, VenTurno, VenTurnoDetalle


class VenTurnoDetalleSerializer(serializers.ModelSerializer):
    cuenta_banco_nombre = serializers.CharField(source='cuenta_banco.nombre', read_only=True, allow_null=True)

    class Meta:
        model = VenTurnoDetalle
        fields = ['id', 'cuenta_banco', 'cuenta_banco_nombre', 'esperado', 'contado', 'diferencia']
        read_only_fields = fields


class VenTurnoSerializer(serializers.ModelSerializer):
    """Solo lectura: el turno se abre y se cierra por sus acciones, no por CRUD."""

    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {
        'id', 'fecha_apertura', 'fecha_cierre', 'estado_cerrado', 'caja_id', 'usuario_id',
        'caja__sede_id',
    }
    select_related_lista = ('caja', 'caja__sede', 'usuario', 'cuenta_banco')
    ordenamiento_default_lista = ('-id',)

    caja_nombre = serializers.CharField(source='caja.nombre', read_only=True, allow_null=True)
    caja_sede_nombre = serializers.CharField(source='caja.sede.nombre', read_only=True, allow_null=True)
    usuario_nombre_corto = serializers.CharField(source='usuario.nombre_corto', read_only=True, allow_null=True)
    cuenta_banco_nombre = serializers.CharField(source='cuenta_banco.nombre', read_only=True, allow_null=True)

    class Meta:
        model = VenTurno
        fields = [
            'id',
            'fecha_apertura',
            'fecha_cierre',
            'base',
            'total_venta',
            'cantidad_documentos',
            'estado_cerrado',
            'comentario',
            'caja',
            'caja_nombre',
            'caja_sede_nombre',
            'usuario',
            'usuario_nombre_corto',
            'cuenta_banco',
            'cuenta_banco_nombre',
        ]
        read_only_fields = fields


class VenTurnoConDetallesSerializer(VenTurnoSerializer):
    """El turno de `GET /turno/{id}/` con su arqueo (vacío mientras está abierto)."""

    detalles = VenTurnoDetalleSerializer(many=True, read_only=True, source='turnos_detalles_turno_rel')

    class Meta(VenTurnoSerializer.Meta):
        fields = VenTurnoSerializer.Meta.fields + ['detalles']
        read_only_fields = fields


class VenTurnoAbrirRequestSerializer(serializers.Serializer):
    caja = serializers.PrimaryKeyRelatedField(queryset=VenCaja.objects.all())
    base = serializers.DecimalField(max_digits=20, decimal_places=6, required=False, default=0)
    cuenta_banco = serializers.PrimaryKeyRelatedField(
        queryset=GenCuentaBanco.objects.all(), required=False, allow_null=True,
        help_text='Dónde queda la base; obligatoria si la base es mayor que cero.',
    )


class VenTurnoContadoSerializer(serializers.Serializer):
    cuenta_banco = serializers.PrimaryKeyRelatedField(queryset=GenCuentaBanco.objects.all())
    valor = serializers.DecimalField(max_digits=20, decimal_places=6)


class VenTurnoCerrarRequestSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, help_text='Id del turno.')
    contados = VenTurnoContadoSerializer(many=True)
    comentario = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)


class VenTurnoResumenCuentaSerializer(serializers.Serializer):
    cuenta_banco = serializers.IntegerField()
    cuenta_banco_nombre = serializers.CharField()
    esperado = serializers.DecimalField(max_digits=20, decimal_places=6)


class VenTurnoResumenSerializer(serializers.Serializer):
    total_venta = serializers.DecimalField(max_digits=20, decimal_places=6)
    cantidad_documentos = serializers.IntegerField()
    cuentas = VenTurnoResumenCuentaSerializer(many=True)
