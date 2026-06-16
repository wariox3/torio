from general.models import GenDocumentoDetalle
from general.servicios.documento import sincronizar_impuestos


def crear_detalle(documento, datos):
    """Crea un detalle ya validado sobre un documento existente (sin recalcular el documento)."""
    datos = dict(datos)
    impuestos = datos.pop('impuestos_ids', [])
    datos.pop('documento', None)  # el documento lo fija el padre
    detalle = GenDocumentoDetalle(documento=documento, **datos)
    detalle.save()
    sincronizar_impuestos(detalle, impuestos)
    detalle.calcular()
    detalle.save()
    return detalle
