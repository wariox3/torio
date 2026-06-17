import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from general.models import GenDocumento, GenDocumentoDetalle, GenDocumentoImpuesto, GenDocumentoTipo


def sincronizar_impuestos(detalle, impuestos):
    """Reemplaza los impuestos de un detalle por la lista de GenImpuesto dada."""
    detalle.documentos_impuestos_documento_detalle_rel.all().delete()
    for impuesto in impuestos:
        GenDocumentoImpuesto.objects.create(
            documento_detalle=detalle,
            impuesto=impuesto,
            porcentaje=impuesto.porcentaje,
            porcentaje_base=impuesto.porcentaje_base,
        )


def aprobar(documento_id):
    """Aprueba un documento: valida estado, asigna consecutivo si falta y marca aprobado."""
    with transaction.atomic():
        # Trae el documento bloqueando la fila para evitar aprobaciones concurrentes.
        try:
            documento = GenDocumento.objects.select_for_update().get(pk=documento_id)
        except GenDocumento.DoesNotExist:
            raise NotFound('Documento no encontrado.')

        # No se puede aprobar un documento anulado ni uno ya aprobado.
        if documento.estado_anulado:
            raise ValidationError('El documento está anulado.')
        if documento.estado_aprobado:
            raise ValidationError('El documento ya está aprobado.')

        # Si el documento aún no tiene número, toma el consecutivo de su tipo y lo incrementa.
        campos_actualizar = ['estado_aprobado']
        if documento.numero is None:
            documento_tipo = GenDocumentoTipo.objects.select_for_update().get(
                pk=documento.documento_tipo_id
            )
            documento.numero = documento_tipo.consecutivo
            documento_tipo.consecutivo += 1
            documento_tipo.save(update_fields=['consecutivo'])
            campos_actualizar.append('numero')

        # Recorre los detalles y agrupa por detalle afectado cuánto se va a afectar.
        # Bloquea cada detalle afectado para que su pendiente no cambie entre validar y aplicar.
        afectados = {}
        totales_a_afectar = {}
        for detalle in documento.documentos_detalles_documento_rel.all():
            afectado_id = detalle.documento_detalle_afectado_id
            if afectado_id is None:
                continue
            if afectado_id not in afectados:
                afectados[afectado_id] = GenDocumentoDetalle.objects.select_for_update().get(
                    pk=afectado_id
                )
                totales_a_afectar[afectado_id] = Decimal('0')
            totales_a_afectar[afectado_id] += detalle.total

        # Valida primero todo: si algún afectado se sobrepasa de su pendiente, corta sin aplicar nada.
        for afectado_id, total_a_afectar in totales_a_afectar.items():
            afectado = afectados[afectado_id]
            if total_a_afectar > afectado.pendiente:
                raise ValidationError(
                    f'El detalle {afectado_id} solo tiene {afectado.pendiente} pendiente '
                    f'por afectar y se intentan afectar {total_a_afectar}.'
                )

        # Validación superada: suma lo afectado a cada detalle afectado (el save recalcula su pendiente).
        for afectado_id, total_a_afectar in totales_a_afectar.items():
            afectado = afectados[afectado_id]
            afectado.afectado += total_a_afectar
            afectado.save(update_fields=['afectado'])

        # Marca el documento como aprobado (y guarda el número si se asignó arriba).
        documento.estado_aprobado = True
        documento.save(update_fields=campos_actualizar)
    return documento


def desaprobar(documento_id):
    """Desaprueba un documento: valida estado y quita el aprobado (conserva el número)."""
    with transaction.atomic():
        try:
            documento = GenDocumento.objects.select_for_update().get(pk=documento_id)
        except GenDocumento.DoesNotExist:
            raise NotFound('Documento no encontrado.')
        if not documento.estado_aprobado:
            raise ValidationError('El documento no está aprobado.')
        if documento.estado_contabilizado:
            raise ValidationError('El documento está contabilizado.')
        if documento.estado_electronico_enviado:
            raise ValidationError('El documento ya fue enviado electrónicamente.')

        # Recorre los detalles y agrupa por detalle afectado cuánto se va a revertir.
        # Bloquea cada detalle afectado para actualizar su afectado de forma segura.
        afectados = {}
        totales_a_afectar = {}
        for detalle in documento.documentos_detalles_documento_rel.all():
            afectado_id = detalle.documento_detalle_afectado_id
            if afectado_id is None:
                continue
            if afectado_id not in afectados:
                afectados[afectado_id] = GenDocumentoDetalle.objects.select_for_update().get(
                    pk=afectado_id
                )
                totales_a_afectar[afectado_id] = Decimal('0')
            totales_a_afectar[afectado_id] += detalle.total

        # Revierte: resta lo afectado a cada detalle afectado (el save recalcula su pendiente).
        for afectado_id, total_a_afectar in totales_a_afectar.items():
            afectado = afectados[afectado_id]
            afectado.afectado -= total_a_afectar
            afectado.save(update_fields=['afectado'])

        # Quita el estado aprobado (conserva el número ya asignado).
        documento.estado_aprobado = False
        documento.save(update_fields=['estado_aprobado'])
    return documento


def generar(documento_tipo_origen, documento_tipo_destino_id, anio, mes, documento_ids=None):
    fecha = date(anio, mes, calendar.monthrange(anio, mes)[1])
    fecha_origen = date(anio + mes // 12, mes % 12 + 1, 1)
    def clonar(instancia, excluir, overrides):
        """Construye una copia sin guardar, omitiendo `excluir` y aplicando `overrides`."""
        datos = {
            campo.attname: getattr(instancia, campo.attname)
            for campo in instancia._meta.concrete_fields
            if not campo.primary_key and campo.name not in excluir
        }
        datos.update(overrides)
        return type(instancia)(**datos)

    excluir_documento = {
        'id', 'numero', 'fecha', 'fecha_validacion',
        'documento_tipo', 'documento_referencia',
        'cue', 'qr', 'referencia_cue', 'referencia_numero', 'referencia_prefijo',
        'electronico_id',
        'evento_documento', 'evento_recepcion', 'evento_aceptacion',
        'estado_aprobado', 'estado_anulado', 'estado_contabilizado',
        'estado_electronico', 'estado_electronico_enviado',
        'estado_electronico_notificado', 'estado_electronico_evento',
        'estado_electronico_descartado',
    }
    excluir_detalle = {'id', 'documento', 'documento_detalle_afectado'}
    excluir_impuesto = {'id', 'documento_detalle'}

    qs = GenDocumento.objects.filter(
        documento_tipo=documento_tipo_origen,
        fecha__lte=fecha,
    )
    if documento_ids:
        qs = qs.filter(id__in=documento_ids)
    qs = qs.prefetch_related(
        'documentos_detalles_documento_rel__documentos_impuestos_documento_detalle_rel',
    )
    documentos = list(qs)

    if not documentos:
        raise ValidationError({'detail': 'No hay documentos para generar.'})

    generados = []
    with transaction.atomic():
        for origen in documentos:
            nuevo = clonar(origen, excluir_documento, {
                'documento_tipo_id': documento_tipo_destino_id,
                'fecha': fecha,
                'documento_referencia_id': origen.id,
            })
            nuevo.save()
            for detalle in origen.documentos_detalles_documento_rel.all():
                nuevo_detalle = clonar(detalle, excluir_detalle, {'documento_id': nuevo.id})
                nuevo_detalle.save()
                for impuesto in detalle.documentos_impuestos_documento_detalle_rel.all():
                    clonar(impuesto, excluir_impuesto, {
                        'documento_detalle_id': nuevo_detalle.id,
                    }).save()
            nuevo.recalcular_totales()
            nuevo.save()

            origen.fecha = fecha_origen
            origen.save(update_fields=['fecha'])

            generados.append(nuevo)

    return generados
