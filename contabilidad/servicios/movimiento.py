from decimal import Decimal

from django.db.models import Sum

from contabilidad.models import ConMovimiento
from general.models import GenDocumento

# Diferencia máxima permitida entre débito y crédito de un comprobante (ajuste por redondeo).
TOLERANCIA_DESCUADRE = Decimal('1')


def analizar_inconsistencias(periodo=None):
    """Revisa los movimientos y devuelve la lista de inconsistencias encontradas.

    Con ``periodo`` la revisión se acota a ese periodo —es lo que necesita el bloqueo, que
    decide sobre un periodo—; sin él revisa la contabilidad entera, para consultarla sin
    tener que ir periodo por periodo.

    Cada inconsistencia comparte la misma forma (``comprobante_id``, ``comprobante_nombre``,
    ``numero``, ``cuenta_id``, ``documento_id``, ``documento_tipo_nombre``, ``inconsistencia``),
    con ``None`` donde no aplique.
    Una lista vacía significa que lo revisado está consistente; para un periodo, que puede
    bloquearse.
    """
    inconsistencias = []
    movimientos_periodo = (
        ConMovimiento.objects.all() if periodo is None
        else ConMovimiento.objects.filter(periodo=periodo)
    )

    # 1. Descuadre: por comprobante, el débito debe igualar al crédito. El asiento es
    # (comprobante, numero) y no se parte entre periodos, así que agrupar sin acotar el
    # periodo da los mismos grupos, no unos más grandes.
    comprobantes = (
        movimientos_periodo
        .values('comprobante_id', 'comprobante__nombre', 'numero')
        .annotate(total_debito=Sum('debito'), total_credito=Sum('credito'))
    )
    for comprobante in comprobantes:
        diferencia = comprobante['total_debito'] - comprobante['total_credito']
        if abs(diferencia) > TOLERANCIA_DESCUADRE:
            inconsistencias.append({
                'comprobante_id': comprobante['comprobante_id'],
                'comprobante_nombre': comprobante['comprobante__nombre'],
                'numero': comprobante['numero'],
                'cuenta_id': None,
                'documento_id': None,
                'documento_tipo_nombre': None,
                'inconsistencia': 'El total de débito y crédito no coinciden',
            })

    # 2. Reglas por movimiento según la configuración de la cuenta.
    movimientos = movimientos_periodo.values(
        'comprobante_id',
        'comprobante__nombre',
        'numero',
        'cuenta_id',
        'centro_costo_id',
        'contacto_id',
        'base',
        'documento_id',
        'cuenta__codigo',
        'cuenta__permite_movimiento',
        'cuenta__exige_centro_costo',
        'cuenta__exige_contacto',
        'cuenta__exige_base',
        'documento__documento_tipo__nombre',
    )
    for movimiento in movimientos:
        base = {
            'comprobante_id': movimiento['comprobante_id'],
            'comprobante_nombre': movimiento['comprobante__nombre'],
            'numero': movimiento['numero'],
            'cuenta_id': movimiento['cuenta_id'],
            'documento_id': movimiento['documento_id'],
            'documento_tipo_nombre': movimiento['documento__documento_tipo__nombre'],
        }
        codigo = movimiento['cuenta__codigo']

        # Las tres exigencias se revisan en los dos sentidos: lo que la cuenta exige
        # tiene que estar, y lo que no exige no puede estar. La mitad sobrante no es
        # inofensiva —un centro de costo colgado de una cuenta que no lo pide sale en
        # los informes por centro de costo y descuadra contra el balance—, y además
        # delata que el movimiento no salió de `contabilizar`, que ya lo anula.
        if not movimiento['cuenta__permite_movimiento']:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} no permite movimientos y tiene movimientos en el periodo',
            })
        if movimiento['cuenta__exige_centro_costo'] and movimiento['centro_costo_id'] is None:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} exige centro de costo y no tiene centro de costo',
            })
        elif not movimiento['cuenta__exige_centro_costo'] and movimiento['centro_costo_id'] is not None:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} no exige centro de costo y tiene centro de costo',
            })
        if movimiento['cuenta__exige_contacto'] and movimiento['contacto_id'] is None:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} exige contacto y no tiene contacto',
            })
        elif not movimiento['cuenta__exige_contacto'] and movimiento['contacto_id'] is not None:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} no exige contacto y tiene contacto',
            })
        # La base es un importe, no una FK: ausente y cero son el mismo estado
        # (`base` es `default=0` y no admite nulo), así que sobra la que no es cero.
        if movimiento['cuenta__exige_base'] and not movimiento['base']:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} exige base y no tiene base',
            })
        elif not movimiento['cuenta__exige_base'] and movimiento['base']:
            inconsistencias.append({
                **base,
                'inconsistencia': f'La cuenta {codigo} no exige base y tiene base',
            })

    # 3. Documentos contables que aún no se han contabilizado, del periodo o de todos.
    # Va uno por documento y no un resumen por tipo: quien revisa tiene que poder
    # abrir el documento que falta, y el tipo solo dice dónde buscarlo.
    documentos = GenDocumento.objects.filter(
        documento_tipo__contabilidad=True,
        estado_contabilizado=False,
    )
    if periodo is not None:
        documentos = documentos.filter(fecha__year=periodo.anio, fecha__month=periodo.mes)
    documentos = documentos.order_by('fecha', 'numero', 'id').values(
        'id', 'numero', 'documento_tipo__nombre',
    )
    for documento in documentos:
        # `numero` es nulo mientras el documento no se aprueba, y ahí el id es lo
        # único con lo que el usuario puede encontrarlo.
        numero = documento['numero']
        etiqueta = f'número {numero}' if numero is not None else f'id {documento["id"]}'
        inconsistencias.append({
            'comprobante_id': None,
            # El documento sin contabilizar todavía no tiene asiento: no hay
            # comprobante que nombrar.
            'comprobante_nombre': None,
            'numero': numero,
            'cuenta_id': None,
            'documento_id': documento['id'],
            'documento_tipo_nombre': documento['documento_tipo__nombre'],
            'inconsistencia': (
                f'El documento de tipo {documento["documento_tipo__nombre"]} '
                f'{etiqueta} no está contabilizado'
            ),
        })

    return inconsistencias
