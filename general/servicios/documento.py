from general.models import GenDocumentoImpuesto


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
