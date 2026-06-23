from decimal import Decimal

from django.db.models import Sum

from contabilidad.models import ConMovimiento
from general.models import GenDocumento

# Diferencia máxima permitida entre débito y crédito de un comprobante (ajuste por redondeo).
TOLERANCIA_DESCUADRE = Decimal('1')


def analizar_inconsistencias(periodo):
    """Revisa los movimientos de un periodo y devuelve la lista de inconsistencias encontradas.

    Cada inconsistencia comparte la misma forma (``comprobante_id``, ``numero``, ``cuenta_id``,
    ``documento_id``, ``documento_tipo_nombre``, ``inconsistencia``), con ``None`` donde no aplique.
    Una lista vacía significa que el periodo está consistente y puede bloquearse.
    """
    inconsistencias = []

    # 1. Descuadre: por comprobante, el débito debe igualar al crédito.
    comprobantes = (
        ConMovimiento.objects.filter(periodo=periodo)
        .values('comprobante_id', 'numero')
        .annotate(total_debito=Sum('debito'), total_credito=Sum('credito'))
    )
    for comprobante in comprobantes:
        diferencia = comprobante['total_debito'] - comprobante['total_credito']
        if abs(diferencia) > TOLERANCIA_DESCUADRE:
            inconsistencias.append({
                'comprobante_id': comprobante['comprobante_id'],
                'numero': comprobante['numero'],
                'cuenta_id': None,
                'documento_id': None,
                'documento_tipo_nombre': None,
                'inconsistencia': 'El total de débito y crédito no coinciden',
            })

    # 2. Reglas por movimiento según la configuración de la cuenta.
    movimientos = ConMovimiento.objects.filter(periodo=periodo).values(
        'comprobante_id',
        'numero',
        'cuenta_id',
        'centro_costo_id',
        'contacto_id',
        'base',
        'documento_id',
        'cuenta__codigo',
        'cuenta__permite_movimiento',
        'cuenta__exige_grupo',
        'cuenta__exige_contacto',
        'cuenta__exige_base',
        'documento__documento_tipo__nombre',
    )
    for movimiento in movimientos:
        base = {
            'comprobante_id': movimiento['comprobante_id'],
            'numero': movimiento['numero'],
            'cuenta_id': movimiento['cuenta_id'],
            'documento_id': movimiento['documento_id'],
            'documento_tipo_nombre': movimiento['documento__documento_tipo__nombre'],
        }
        codigo = movimiento['cuenta__codigo']

        if not movimiento['cuenta__permite_movimiento']:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} no permite movimientos y tiene movimientos en el periodo',
            })
        if movimiento['cuenta__exige_grupo'] and movimiento['centro_costo_id'] is None:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} exige grupo y no tiene grupo',
            })
        if movimiento['cuenta__exige_contacto'] and movimiento['contacto_id'] is None:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} exige contacto y no tiene contacto',
            })
        if movimiento['cuenta__exige_base'] and not movimiento['base']:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} exige base y no tiene base',
            })

    # 3. Documentos contables del periodo que aún no se han contabilizado.
    tipos_sin_contabilizar = (
        GenDocumento.objects.filter(
            documento_tipo__contabilidad=True,
            fecha__year=periodo.anio,
            fecha__month=periodo.mes,
            estado_contabilizado=False,
        )
        .values_list('documento_tipo__nombre', flat=True)
        .distinct()
    )
    if tipos_sin_contabilizar:
        inconsistencias.append({
            'comprobante_id': None,
            'numero': None,
            'cuenta_id': None,
            'documento_id': None,
            'documento_tipo_nombre': None,
            'inconsistencia': (
                'Existen documentos sin contabilizar en el periodo en los siguientes '
                f'tipos de documento: {", ".join(tipos_sin_contabilizar)}'
            ),
        })

    return inconsistencias
