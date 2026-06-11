import calendar
from datetime import date

from django.db import transaction
from rest_framework.exceptions import ValidationError

from general.models import GenDocumento, GenDocumentoImpuesto


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


def generar_documentos(documento_tipo_origen, documento_tipo_destino_id, anio, mes, documento_ids=None):
    fecha = date(anio, mes, calendar.monthrange(anio, mes)[1])
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
    excluir_detalle = {'id', 'documento', 'documento_afectado', 'documento_detalle_afectado'}
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

            origen.fecha = fecha
            origen.save(update_fields=['fecha'])

            generados.append(nuevo)

    return generados
