"""
Validación de la cartera, cuentas por cobrar y por pagar, y su resumen.

`GenDocumento.pago`, `afectado` y `pendiente` se mantienen por incrementos:
aprobar, desaprobar, anular y cada pago suman o restan sobre lo que ya había. Si
alguno de esos caminos falla a medias o un dato se toca por fuera, el saldo queda
mal para siempre, porque nada lo vuelve a calcular desde cero. Este módulo sí lo
hace, a partir de lo que originó cada valor:

- `pago`: la suma de los `GenDocumentoPago` no anulados del documento.
- `afectado`: lo que otros documentos le descuentan —las líneas con
  `documento_afectado` de documentos aprobados y no anulados (recibos y
  egresos), que cuentan por su `precio` como en `_agrupar_documentos_afectados`,
  y las notas crédito aprobadas que lo referencian, por su `total - pago`—. Una
  nota crédito con referencia se descarga además a sí misma por ese mismo valor
  (`_afectar_documento_referencia`).
- `pendiente`: `total - (afectado + pago)` si el documento está aprobado y no
  anulado; si no, cero (`_quitar_cartera`, `anular`).

Se corre por un lado de la cartera a la vez: `cobrar` o `pagar`, los mismos
indicadores del tipo de documento que usan los informes de cartera. Dentro de
ese lado solo entran las clases con cartera (`DOCUMENTO_CLASES_CON_CARTERA`),
que son las únicas a las que aprobar les asigna saldo. El detalle tiene su propia
afectación (`documento_detalle_afectado`), que no alimenta la del documento y no
se toca acá.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from general.models import GenDocumento, GenDocumentoDetalle, GenDocumentoPago
from general.servicios.documento import (
    DOCUMENTO_CLASES_CON_CARTERA,
    DOCUMENTO_TIPOS_NOTA_CREDITO,
)

CAMPOS_CARTERA = ('pago', 'afectado', 'pendiente')

# Lado de la cartera → indicador de `GenDocumentoTipo` que lo marca.
TIPOS = {
    'cobrar': 'documento_tipo__cobrar',
    'pagar': 'documento_tipo__pagar',
}


def _documentos(tipo):
    return GenDocumento.objects.filter(
        documento_tipo__documento_clase_id__in=DOCUMENTO_CLASES_CON_CARTERA,
        **{TIPOS[tipo]: True},
    ).order_by('id')


def _esperados():
    """
    Calcula `pago` y `afectado` de todos los documentos desde su origen.

    Los `order_by()` vacíos no sobran: los modelos ordenan por `-id`, y ese orden
    se metería en el GROUP BY y devolvería una fila por registro en vez de una
    por documento.
    """
    pagos = dict(
        GenDocumentoPago.objects
        .filter(estado_anulado=False)
        .order_by()
        .values('documento_id')
        .annotate(total=Sum('pago'))
        .values_list('documento_id', 'total')
    )

    afectados = defaultdict(Decimal)
    lineas = (
        GenDocumentoDetalle.objects
        .filter(
            documento_afectado__isnull=False,
            documento__estado_aprobado=True,
            documento__estado_anulado=False,
        )
        .order_by()
        .values('documento_afectado_id')
        .annotate(total=Sum('precio'))
        .values_list('documento_afectado_id', 'total')
    )
    for documento_id, total in lineas:
        afectados[documento_id] += total

    notas = (
        GenDocumento.objects
        .filter(
            documento_tipo_id__in=DOCUMENTO_TIPOS_NOTA_CREDITO,
            documento_referencia__isnull=False,
            estado_aprobado=True,
            estado_anulado=False,
        )
        .order_by()
        .values_list('id', 'documento_referencia_id', 'total', 'pago')
    )
    for nota_id, referencia_id, total, pago in notas:
        afectados[referencia_id] += total - pago
        afectados[nota_id] += total - pago

    return pagos, afectados


def _diferencias(documento, pagos, afectados):
    """Lo que el documento debería tener en cada campo que difiere de lo guardado."""
    pago = pagos.get(documento.id) or Decimal('0')
    afectado = afectados.get(documento.id, Decimal('0'))
    if documento.estado_aprobado and not documento.estado_anulado:
        pendiente = documento.total - (afectado + pago)
    else:
        pendiente = Decimal('0')

    esperado = {'pago': pago, 'afectado': afectado, 'pendiente': pendiente}
    return {
        campo: valor
        for campo, valor in esperado.items()
        if getattr(documento, campo) != valor
    }


def validar(tipo):
    """
    Recalcula la cartera de un lado y corrige los documentos que difieren; los
    que cuadran no se tocan.

    Los documentos se bloquean antes de calcular: así una aprobación o un pago que
    llegue en el medio espera a que esto termine, en vez de mover un saldo que acá
    se va a sobrescribir con un cálculo que no lo vio.
    """
    with transaction.atomic():
        documentos = list(_documentos(tipo).select_for_update(of=('self',)))
        pagos, afectados = _esperados()

        corregidos = []
        for documento in documentos:
            diferencias = _diferencias(documento, pagos, afectados)
            if diferencias:
                for campo, valor in diferencias.items():
                    setattr(documento, campo, valor)
                corregidos.append(documento)
        GenDocumento.objects.bulk_update(corregidos, CAMPOS_CARTERA)


# ------------------------------------------------------------------ resumen ----

# Rangos de antigüedad: (clave, días vencidos desde, hasta). `None` es abierto.
RANGOS_ANTIGUEDAD = (
    ('al_dia', None, 0),
    ('1_30', 1, 30),
    ('31_60', 31, 60),
    ('61_90', 61, 90),
    ('mas_90', 91, None),
)

# Ventana de ventas (o compras) contra la que se miden los días de cartera.
DIAS_DSO = 90

LIMITE_LISTAS = 10


def _pendientes(tipo):
    """
    Lo mismo que listan los informes `cobrar_pendiente` y `pagar_pendiente`: así
    el front puede abrir el informe desde cualquier cifra del resumen y ver
    exactamente los documentos que la suman.

    `vence` es `fecha_vence`, o `fecha` si no la tiene: un documento sin plazo
    vence el mismo día, como lo fecha `generar_recurrente`.
    """
    return GenDocumento.objects.filter(
        pendiente__gt=0,
        estado_aprobado=True,
        estado_anulado=False,
        **{TIPOS[tipo]: True},
    ).annotate(vence=Coalesce('fecha_vence', 'fecha')).order_by()


def _filtro_rango(hoy, desde, hasta):
    """Q de los documentos con entre `desde` y `hasta` días vencidos."""
    filtro = Q()
    if desde is not None:
        filtro &= Q(vence__lte=hoy - timedelta(days=desde))
    if hasta is not None:
        filtro &= Q(vence__gte=hoy - timedelta(days=hasta))
    return filtro


def _ventas(tipo, hoy):
    """
    Lo facturado (o comprado) en los últimos `DIAS_DSO` días, neto de notas
    crédito: una nota devuelve venta, no la suma.
    """
    totales = GenDocumento.objects.filter(
        estado_aprobado=True,
        estado_anulado=False,
        documento_tipo__documento_clase_id__in=DOCUMENTO_CLASES_CON_CARTERA,
        fecha__gt=hoy - timedelta(days=DIAS_DSO),
        fecha__lte=hoy,
        **{TIPOS[tipo]: True},
    ).aggregate(
        brutas=Sum('total', filter=~Q(documento_tipo_id__in=DOCUMENTO_TIPOS_NOTA_CREDITO)),
        notas=Sum('total', filter=Q(documento_tipo_id__in=DOCUMENTO_TIPOS_NOTA_CREDITO)),
    )
    return (totales['brutas'] or Decimal('0')) - (totales['notas'] or Decimal('0'))


def resumen(tipo, hoy=None):
    """
    Cifras del tablero de cartera de un lado (`cobrar` o `pagar`).

    Todo se agrega en la base: los indicadores y la antigüedad salen de un solo
    `aggregate`, y cada lista de una consulta más.
    """
    hoy = hoy or timezone.localdate()
    pendientes = _pendientes(tipo)
    vencidos = Q(vence__lt=hoy)

    agregados = pendientes.aggregate(
        total=Sum('pendiente'),
        documentos=Count('id'),
        vencido=Sum('pendiente', filter=vencidos),
        por_vencer_7=Sum(
            'pendiente', filter=Q(vence__gte=hoy, vence__lte=hoy + timedelta(days=7)),
        ),
        **{
            f'rango_{clave}': Sum('pendiente', filter=_filtro_rango(hoy, desde, hasta))
            for clave, desde, hasta in RANGOS_ANTIGUEDAD
        },
        **{
            f'cantidad_{clave}': Count('id', filter=_filtro_rango(hoy, desde, hasta))
            for clave, desde, hasta in RANGOS_ANTIGUEDAD
        },
    )
    cero = Decimal('0')
    total = agregados['total'] or cero

    # Días que tarda en promedio en cobrarse (o pagarse) lo facturado. Sin ventas
    # en la ventana no hay contra qué medir.
    ventas = _ventas(tipo, hoy)
    dso = round(total / ventas * DIAS_DSO) if ventas > 0 else None

    top_contactos = list(
        pendientes
        .values('contacto_id', 'contacto__nombre_corto', 'contacto__numero_identificacion')
        .annotate(
            saldo=Sum('pendiente'),
            vencido=Coalesce(Sum('pendiente', filter=vencidos), cero),
            documentos=Count('id'),
        )
        .order_by('-saldo', 'contacto_id')[:LIMITE_LISTAS]
    )

    mas_vencidos = list(
        pendientes
        .filter(vencidos)
        .values(
            'id', 'numero', 'fecha', 'vence', 'pendiente',
            'documento_tipo__nombre', 'contacto_id', 'contacto__nombre_corto',
        )
        .order_by('vence', 'id')[:LIMITE_LISTAS]
    )

    return {
        'fecha': hoy,
        'total': total,
        'documentos': agregados['documentos'],
        'vencido': agregados['vencido'] or cero,
        'por_vencer_7': agregados['por_vencer_7'] or cero,
        'dso': dso,
        'antiguedad': [
            {
                'rango': clave,
                'dias_desde': desde,
                'dias_hasta': hasta,
                'valor': agregados[f'rango_{clave}'] or cero,
                'documentos': agregados[f'cantidad_{clave}'],
            }
            for clave, desde, hasta in RANGOS_ANTIGUEDAD
        ],
        'top_contactos': [
            {
                'contacto_id': fila['contacto_id'],
                'contacto_nombre_corto': fila['contacto__nombre_corto'],
                'contacto_numero_identificacion': fila['contacto__numero_identificacion'],
                'saldo': fila['saldo'],
                'vencido': fila['vencido'],
                'documentos': fila['documentos'],
            }
            for fila in top_contactos
        ],
        'mas_vencidos': [
            {
                'id': fila['id'],
                'numero': fila['numero'],
                'documento_tipo_nombre': fila['documento_tipo__nombre'],
                'contacto_id': fila['contacto_id'],
                'contacto_nombre_corto': fila['contacto__nombre_corto'],
                'fecha': fila['fecha'],
                'fecha_vence': fila['vence'],
                'dias_vencido': (hoy - fila['vence']).days,
                'pendiente': fila['pendiente'],
            }
            for fila in mas_vencidos
        ],
    }
