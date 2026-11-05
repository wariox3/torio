"""El PDF del informe de cierre de un turno (ver `venta/formatos/turno_cierre.py`)."""
import io

from reportlab.platypus import BaseDocTemplate

from utilidades.formatos.pagina import PAGINA, CanvasNumerado, MarcaDocumento, plantilla_rollo
from venta.formatos import FormatoTurnoCierre


def pdf_turno(turno):
    """Devuelve (contenido, nombre del archivo)."""
    elementos = [
        MarcaDocumento(f'turno_{turno.id}', FormatoTurnoCierre.numerar_paginas),
        *FormatoTurnoCierre(turno).construir(),
    ]
    buffer = io.BytesIO()
    BaseDocTemplate(
        buffer, pagesize=PAGINA, pageTemplates=[plantilla_rollo('turno', elementos)],
    ).build(elementos, canvasmaker=CanvasNumerado)
    prefijo = 'cierre' if turno.estado_cerrado else 'precierre'
    return buffer.getvalue(), f'{prefijo}_turno_{turno.id}.pdf'
