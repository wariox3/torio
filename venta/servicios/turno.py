"""
Turnos de caja: abrir, ver lo esperado y cerrar con el arqueo.

Reglas:

- Una caja tiene a lo sumo un turno abierto (lo garantiza la restricción
  `ven_turno_un_abierto_por_caja`), y un cajero también: si cambia el cajero, se
  cierra el turno y se abre otro.
- Solo la factura POS lleva turno, y no se crea sin uno abierto del mismo cajero
  (`GenDocumentoSerializer._validar_turno`).
- Lo esperado de cada cuenta bancaria es la suma de los pagos no anulados de las
  facturas no anuladas del turno, más la base en la cuenta donde quedó. No hay
  otra forma de armarlo: `GenDocumentoPago` no tiene fecha.
- Al cerrar se guarda el arqueo (`VenTurnoDetalle`) y los totales, y no se
  recalculan: lo que se anule después no cambia el cierre.

Orden de bloqueo: primero el turno. Así lo hacen el cierre y la creación de la
factura POS, para que no entre una venta mientras se calcula el arqueo.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from general.models import GenCuentaBanco, GenDocumento, GenDocumentoPago
from utilidades.moneda import redondear_moneda
from venta.models import VenTurno, VenTurnoDetalle


def abrir(caja, usuario, base, cuenta_banco):
    if not caja.estado_activo:
        raise ValidationError({'detail': f'La caja {caja.nombre} está inactiva.'})
    base = redondear_moneda(base or Decimal('0'))
    if base < 0:
        raise ValidationError({'detail': 'La base no puede ser negativa.'})
    if base > 0 and cuenta_banco is None:
        raise ValidationError({'detail': 'Indique la cuenta bancaria donde queda la base.'})
    if VenTurno.objects.filter(usuario=usuario.email, estado_cerrado=False).exists():
        raise ValidationError({'detail': 'Ya tiene un turno abierto: ciérrelo antes de abrir otro.'})

    try:
        with transaction.atomic():
            return VenTurno.objects.create(
                caja=caja,
                usuario=usuario.email,
                base=base,
                cuenta_banco=cuenta_banco,
                fecha_apertura=timezone.now(),
            )
    except IntegrityError:
        raise ValidationError({'detail': f'La caja {caja.nombre} ya tiene un turno abierto.'})


def esperado(turno):
    """{cuenta_banco_id: valor esperado} del turno, con la base incluida."""
    pagos = (
        GenDocumentoPago.objects
        .filter(documento__turno=turno, estado_anulado=False, documento__estado_anulado=False)
        .values('cuenta_banco_id')
        .annotate(total=Sum('pago'))
    )
    resultado = {fila['cuenta_banco_id']: fila['total'] for fila in pagos}
    if turno.cuenta_banco_id is not None:
        resultado[turno.cuenta_banco_id] = resultado.get(turno.cuenta_banco_id, Decimal('0')) + turno.base
    return resultado


def totales(turno):
    """Lo vendido en el turno: total y cantidad de facturas no anuladas."""
    datos = (
        GenDocumento.objects
        .filter(turno=turno, estado_anulado=False)
        .aggregate(total=Sum('total'), cantidad=Count('id'))
    )
    return datos['total'] or Decimal('0'), datos['cantidad']


def cerrar(turno_id, contados, comentario=None):
    """
    `contados`: lista de `(cuenta_banco, valor)`. Tiene que traer toda cuenta con
    algo esperado; puede traer otras, con esperado en cero (plata que apareció).
    """
    with transaction.atomic():
        try:
            turno = VenTurno.objects.select_for_update().get(pk=turno_id)
        except VenTurno.DoesNotExist:
            raise NotFound('Turno no encontrado.')
        if turno.estado_cerrado:
            raise ValidationError({'detail': 'El turno ya está cerrado.'})

        sin_aprobar = GenDocumento.objects.filter(
            turno=turno, estado_aprobado=False, estado_anulado=False,
        ).count()
        if sin_aprobar:
            raise ValidationError({
                'detail': f'El turno tiene {sin_aprobar} factura(s) sin aprobar: apruébelas o elimínelas antes de cerrar.',
            })

        por_cuenta = {}
        for cuenta_banco, valor in contados:
            if cuenta_banco.id in por_cuenta:
                raise ValidationError({'detail': f'La cuenta {cuenta_banco.nombre} está repetida.'})
            if valor < 0:
                raise ValidationError({'detail': f'Lo contado en {cuenta_banco.nombre} no puede ser negativo.'})
            por_cuenta[cuenta_banco.id] = (cuenta_banco, redondear_moneda(valor))

        esperados = esperado(turno)
        faltantes = [cuenta_id for cuenta_id, valor in esperados.items() if valor and cuenta_id not in por_cuenta]
        if faltantes:
            nombres = ', '.join(
                GenCuentaBanco.objects.filter(id__in=faltantes).order_by('nombre').values_list('nombre', flat=True)
            )
            raise ValidationError({'detail': f'Falta lo contado en: {nombres}.'})

        detalles = []
        for cuenta_id, (cuenta_banco, contado) in por_cuenta.items():
            valor_esperado = esperados.get(cuenta_id, Decimal('0'))
            detalles.append(VenTurnoDetalle(
                turno=turno,
                cuenta_banco=cuenta_banco,
                esperado=valor_esperado,
                contado=contado,
                diferencia=contado - valor_esperado,
            ))
        VenTurnoDetalle.objects.bulk_create(detalles)

        turno.total_venta, turno.cantidad_documentos = totales(turno)
        turno.fecha_cierre = timezone.now()
        turno.estado_cerrado = True
        turno.comentario = comentario or None
        turno.save(update_fields=[
            'total_venta', 'cantidad_documentos', 'fecha_cierre', 'estado_cerrado', 'comentario',
        ])
    return turno
