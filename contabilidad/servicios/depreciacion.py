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

El servicio **no toca el activo**: `depreciacion_acumulada` y `depreciacion_saldo`
quedan como están, y el documento es la constancia de lo que se depreció en el
periodo. Por eso el cargue exige un documento sin detalles: si se pudiera
recargar sobre uno ya cargado, el mismo periodo quedaría depreciado dos veces.
"""
import calendar
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError

from contabilidad.models import ConActivo
from general.models import GenDocumento
from general.servicios.documento_detalle import crear_detalle

# Único tipo de documento que recibe el cargue. Mismo id del fixture
# `general/fixtures/11_documento_tipo.json`.
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
        depreciar = activo.depreciacion_periodo
    else:
        # La cuota es en pesos enteros: el prorrateo por días no puede dejar
        # centavos que después no cuadren contra el saldo.
        depreciar = Decimal(round(activo.depreciacion_periodo / DIAS_PERIODO * dias))
    return min(depreciar, activo.depreciacion_saldo)
