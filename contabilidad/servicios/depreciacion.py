"""
Cargue de la depreciación del periodo en un documento.

El documento de depreciación no se digita línea por línea: se crea vacío con su
fecha y este servicio le mete una línea por cada activo que todavía tenga saldo
por depreciar en ese mes. Cada línea es un apunte contable (`tipo_registro='D'`),
que es lo que después lee `contabilizar` para llevar el valor a la cuenta de
depreciación acumulada y a la de gasto del activo.

La liquidación es sobre mes comercial de 30 días: el activo que estuvo el mes
completo deprecia su `depreciacion_periodo` entero, y el que entró o salió a
mitad de mes deprecia la parte proporcional a los días que estuvo.

El cargue **no toca el activo**: lo depreciado solo le llega cuando el documento
se aprueba, y se le devuelve si se desaprueba o se anula (`recalcular_activos`).
Por eso el cargue exige un documento sin detalles: si se pudiera recargar sobre
uno ya cargado, el mismo periodo quedaría depreciado dos veces.

`depreciacion_acumulada` no se lleva sumando y restando: es la suma de las líneas
de depreciación del activo en documentos aprobados y sin anular, y se recalcula
desde ahí cada vez. Así un documento aprobado antes de que esto existiera, o
cualquier descuadre, se corrige solo en vez de arrastrarse.
"""
import calendar
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q, Sum
from rest_framework.exceptions import NotFound, ValidationError

from contabilidad.models import ConActivo
from general.models import GenDocumento, GenDocumentoDetalle
from general.servicios.documento_detalle import crear_detalle
from utilidades.moneda import redondear_moneda

# Único tipo de documento que recibe el cargue. Mismo id del catálogo
# `general/catalogos/11_documento_tipo.json`.
DOCUMENTO_TIPO_DEPRECIACION = 23

# La depreciación se liquida sobre mes comercial: todos los meses valen 30 días,
# sin importar cuántos tenga el calendario.
DIAS_PERIODO = 30


def cargar_activos(documento_id):
    """Carga en el documento una línea por cada activo con saldo por depreciar en su mes."""
    with transaction.atomic():
        # Se bloquea la fila para que dos cargues simultáneos no metan los
        # detalles dos veces: el segundo espera y encuentra el documento ya cargado.
        try:
            documento = GenDocumento.objects.select_for_update().get(pk=documento_id)
        except GenDocumento.DoesNotExist:
            raise NotFound('Documento no encontrado.')

        if documento.documento_tipo_id != DOCUMENTO_TIPO_DEPRECIACION:
            raise ValidationError('El documento no es de depreciación.')
        if not documento.es_mutable():
            raise ValidationError('El documento no es modificable.')
        if documento.fecha is None:
            raise ValidationError('El documento no tiene fecha: de ella sale el periodo a depreciar.')
        if documento.documentos_detalles_documento_rel.exists():
            raise ValidationError(
                'El documento ya tiene detalles. Bórrelos antes de volver a cargar.'
            )

        fecha_desde, fecha_hasta = _periodo(documento.fecha)

        # Activos vivos en el mes: activados a más tardar el último día y sin dar
        # de baja antes del primero. El saldo se filtra en la consulta y no en el
        # ciclo: el activo ya depreciado del todo no tiene línea que aportar.
        activos = ConActivo.objects.filter(
            Q(fecha_baja__isnull=True) | Q(fecha_baja__gte=fecha_desde),
            fecha_activacion__lte=fecha_hasta,
            depreciacion_saldo__gt=0,
        ).order_by('id')

        total = Decimal('0')
        for activo in activos:
            dias = _dias_a_depreciar(activo, fecha_desde, fecha_hasta)
            # El activo dado de baja el mismo día en que abre el mes queda en cero
            # días —y en un mes de 31, hasta en menos—: no estuvo vivo en el
            # periodo, y con días negativos la línea saldría en negativo. El corte
            # es por días y no por valor: un activo que sí estuvo el mes lleva su
            # línea aunque su cuota esté en cero, porque es lo que se cargó.
            if dias <= 0:
                continue
            depreciar = _valor_a_depreciar(activo, dias)
            crear_detalle(documento, {
                'tipo_registro': 'D',
                'contacto_id': documento.contacto_id,
                'centro_costo_id': documento.centro_costo_id,
                'activo': activo,
                'precio': depreciar,
                'dias': dias,
            })
            total += depreciar

        # `recalcular_totales()` no sirve acá: en una línea contable `calcular()`
        # no corre y su `total` queda en cero, así que la suma de los detalles
        # dejaría el documento en cero. Lo que vale es lo depreciado, que es la
        # suma de los `precio`.
        documento.total = total
        documento.save(update_fields=['total'])

    return documento


def recalcular_activos(activo_ids=None):
    """
    Deja `depreciacion_acumulada` y `depreciacion_saldo` de los activos en lo que
    dicen sus documentos; los que ya cuadran no se tocan. Sin `activo_ids`, todos.

    Los activos se bloquean antes de sumar: así una aprobación que llegue en el
    medio espera a que esto termine, en vez de cambiar un saldo que acá se va a
    sobrescribir con un cálculo que no la vio.
    """
    with transaction.atomic():
        activos = ConActivo.objects.select_for_update().order_by('id')
        if activo_ids is not None:
            activos = activos.filter(id__in=activo_ids)
        activos = list(activos)

        acumulados = dict(
            GenDocumentoDetalle.objects.filter(
                tipo_registro='D',
                activo_id__in=[activo.id for activo in activos],
                documento__estado_aprobado=True,
                documento__estado_anulado=False,
            ).values_list('activo_id').annotate(total=Sum('precio'))
        )

        corregidos = []
        for activo in activos:
            acumulada = acumulados.get(activo.id) or Decimal('0')
            saldo = activo.valor_compra - activo.depreciacion_inicial - acumulada
            if (activo.depreciacion_acumulada, activo.depreciacion_saldo) != (acumulada, saldo):
                activo.depreciacion_acumulada = acumulada
                activo.depreciacion_saldo = saldo
                corregidos.append(activo)
        ConActivo.objects.bulk_update(corregidos, ['depreciacion_acumulada', 'depreciacion_saldo'])
    return activos


def _depreciado_por_activo(documento):
    """Cuánto deprecia el documento de cada activo: `{activo_id: valor}`."""
    return dict(
        documento.documentos_detalles_documento_rel
        .filter(tipo_registro='D', activo__isnull=False)
        .values_list('activo_id').annotate(total=Sum('precio'))
    )


def validar_saldo(documento):
    """
    Antes de aprobar: lo que el documento deprecia de cada activo tiene que caber
    en lo que al activo le queda por depreciar.

    El cargue ya topa cada línea en el saldo, pero el saldo de ese momento: dos
    documentos del mismo activo cargados antes de aprobar ninguno caben cada uno
    por su lado y juntos no. El saldo se recalcula acá mismo, para comparar contra
    lo que de verdad queda.
    """
    depreciado = _depreciado_por_activo(documento)
    if not depreciado:
        return
    for activo in recalcular_activos(depreciado.keys()):
        if depreciado[activo.id] > activo.depreciacion_saldo:
            raise ValidationError(
                f'El activo {activo.codigo} - {activo.nombre} solo tiene '
                f'{activo.depreciacion_saldo:,.2f} por depreciar y el documento le '
                f'deprecia {depreciado[activo.id]:,.2f}.'
            )


def afectar_activos(documento):
    """
    Después de aprobar, desaprobar o anular: lleva a los activos del documento lo
    que su nuevo estado significa. Aprobado, les suma lo depreciado; sin aprobar o
    anulado, se lo devuelve. Es el mismo recálculo en los tres casos.
    """
    depreciado = _depreciado_por_activo(documento)
    if depreciado:
        recalcular_activos(depreciado.keys())


def _periodo(fecha):
    """El mes de la fecha del documento, del día 1 al último."""
    ultimo_dia = calendar.monthrange(fecha.year, fecha.month)[1]
    return fecha.replace(day=1), fecha.replace(day=ultimo_dia)


def _dias_a_depreciar(activo, fecha_desde, fecha_hasta):
    """
    Días del mes comercial que le corresponden al activo.

    El que venía de antes y sigue vivo al cierre tiene el mes completo. El que se
    activó dentro del mes cuenta desde su activación hasta el último día, y en
    febrero se le suma lo que le falta al mes para llegar a 30 —si no, un activo
    activado el primero de febrero depreciaría menos que uno activado el primero
    de enero—. El que se dio de baja dentro del mes pierde los días que van de la
    baja al cierre.
    """
    dias = DIAS_PERIODO

    if fecha_desde <= activo.fecha_activacion <= fecha_hasta:
        dias = (fecha_hasta - activo.fecha_activacion).days
        if fecha_hasta.month == 2:
            dias += DIAS_PERIODO - fecha_hasta.day

    if activo.fecha_baja and fecha_desde <= activo.fecha_baja <= fecha_hasta:
        dias -= (fecha_hasta - activo.fecha_baja).days + 1

    # Nunca más de un mes comercial, aunque el calendario tenga 31 días.
    return min(dias, DIAS_PERIODO)


def _valor_a_depreciar(activo, dias):
    """Lo que deprecia el activo por esos días, sin pasarse del saldo que le queda."""
    if dias == DIAS_PERIODO:
        # La cuota del activo guarda 6 decimales (es valor de compra / meses); lo
        # que se deprecia es dinero y va en centavos.
        depreciar = redondear_moneda(activo.depreciacion_periodo)
    else:
        # La cuota es en pesos enteros: el prorrateo por días no puede dejar
        # centavos que después no cuadren contra el saldo. `round()` sería
        # redondeo bancario (0.5 → 0); acá la mitad sube.
        depreciar = (activo.depreciacion_periodo / DIAS_PERIODO * dias).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP,
        )
    return min(depreciar, activo.depreciacion_saldo)
