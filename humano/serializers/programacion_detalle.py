from rest_framework import serializers

from humano.models import HumProgramacionDetalle
from humano.models.programacion_detalle import MENSAJE_PROGRAMACION_CERRADA


class HumProgramacionDetalleSerializer(serializers.ModelSerializer):
    # Config consumida por FiltrosDinamicosMixin
    campos_filtrables = {'id', 'programacion_id', 'contrato_id', 'ingreso', 'retiro'}
    select_related_lista = ('programacion', 'contrato', 'contrato__contacto')
    ordenamiento_default_lista = ('-id',)

    contrato_nombre = serializers.CharField(source='contrato.contacto.nombre_corto', read_only=True, default=None)
    contacto_numero_identificacion = serializers.CharField(
        source='contrato.contacto.numero_identificacion', read_only=True, default=None,
    )

    class Meta:
        model = HumProgramacionDetalle
        fields = [
            'id',
            'fecha_desde',
            'fecha_hasta',
            'dias',
            'dias_transporte',
            'dias_novedad',
            'salario',
            'salario_promedio',
            'base_prestacion',
            'diurna',
            'nocturna',
            'festiva_diurna',
            'festiva_nocturna',
            'extra_diurna',
            'extra_nocturna',
            'extra_festiva_diurna',
            'extra_festiva_nocturna',
            'recargo_nocturno',
            'recargo_festivo_diurno',
            'recargo_festivo_nocturno',
            'pago_horas',
            'pago_auxilio_transporte',
            'pago_incapacidad',
            'pago_licencia',
            'pago_vacacion',
            'descuento_salud',
            'descuento_pension',
            'descuento_fondo_solidaridad',
            'descuento_retencion_fuente',
            'descuento_credito',
            'descuento_embargo',
            'adicional',
            'ingreso',
            'retiro',
            'error_terminacion',
            'base_cotizacion_acumulado',
            'devengado',
            'deduccion',
            'total',
            'deduccion_fondo_pension_acumulado',
            'prima_propuesto',
            'cesantia_propuesto',
            'interes_propuesto',
            'programacion',
            'contrato',
            'contrato_nombre',
            'contacto_numero_identificacion',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        if self.instance is not None:
            # Al editar, el detalle sigue siendo del mismo contrato en la misma
            # programación: moverlo desordena `HumProgramacion.contratos`. Para eso
            # se elimina y se vuelve a cargar.
            for campo in ('programacion', 'contrato'):
                if campo in attrs and attrs[campo] != getattr(self.instance, campo):
                    raise serializers.ValidationError(f'No se puede cambiar el campo {campo} de un detalle.')
        # Generada, sus valores ya están en los documentos de nómina: ni se crean
        # ni se editan detalles.
        programacion = attrs.get('programacion') or self.instance.programacion
        if programacion.estado_aprobado or programacion.estado_generado:
            raise serializers.ValidationError(MENSAJE_PROGRAMACION_CERRADA)
        return attrs
