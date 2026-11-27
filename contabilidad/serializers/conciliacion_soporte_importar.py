import datetime
from decimal import Decimal

from rest_framework import serializers

from contabilidad.models import ConConciliacion, ConConciliacionSoporte
from general.serializers.documento_detalle_importar import _decimal, _texto_o_none

DETALLE_MAX = ConConciliacionSoporte._meta.get_field('detalle').max_length


class ConConciliacionSoporteImportarSerializer(serializers.Serializer):
    """
    Plantilla del extracto bancario de una conciliación.

    Es consumido por `ImportarExcelMixin`, pero se construye con la conciliación
    padre: la resuelve el ViewSet desde el parámetro `conciliacion` (ver
    `ConConciliacionSoporteViewSet`).

    Reglas:
      * Una sola columna `Valor` con signo, como la trae la mayoría de extractos:
        positivo (entra plata al banco) es `debito`, negativo (sale) es `credito`
        —la misma naturaleza del movimiento de la cuenta bancaria en los libros,
        que es contra lo que se cruza—. Cero no es una línea.
      * La fecha debe caer dentro del rango de la conciliación: una línea por
        fuera nunca va a cruzar.
      * El detalle se recorta al largo del modelo en vez de rechazarse: las
        descripciones del banco son largas y el final no aporta.
      * Agrega líneas, no reemplaza: el extracto puede venir en varios archivos.
        Para volver a cargarlo está `limpiar`.

    Todo o nada: si una fila falla no se importa ninguna.
    """

    model = ConConciliacionSoporte
    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    campos_excel = (
        ('fecha', 'Fecha'),
        ('valor', 'Valor'),
        ('detalle', 'Detalle'),
    )
    campos_requeridos = {'fecha', 'valor'}

    def __init__(self, conciliacion, **kwargs):
        super().__init__(**kwargs)
        self.conciliacion = conciliacion
        self.nombre_archivo = f'conciliacion_{conciliacion.id}_soporte'

    @property
    def valores_ejemplo(self):
        return {
            'fecha': (self.conciliacion.fecha_desde, self.conciliacion.fecha_hasta),
            'valor': (1500000, -85000),
            'detalle': ('CONSIGNACION SUCURSAL', 'PAGO PSE PROVEEDOR'),
        }

    def procesar_lote(self, filas_validas):
        """
        Corre dentro del `transaction.atomic()` del mixin, que revierte todo si
        se devuelve algún error.
        """
        if not filas_validas:
            return 0, []

        # Se relee bloqueada: `limpiar` sobre la misma conciliación espera a que
        # esta carga termine en vez de cruzarse con ella.
        conciliacion = ConConciliacion.objects.select_for_update().get(pk=self.conciliacion.pk)

        errores = []
        nuevos = []
        for idx, datos in filas_validas:
            mensajes = []

            fecha = datos.get('fecha')
            if isinstance(fecha, datetime.datetime):
                fecha = fecha.date()
            # La fase estructural ya garantizó que es una fecha.
            if not (conciliacion.fecha_desde <= fecha <= conciliacion.fecha_hasta):
                mensajes.append(
                    f'La fecha {fecha} está fuera de la conciliación '
                    f'({conciliacion.fecha_desde} a {conciliacion.fecha_hasta})'
                )

            valor = None
            if isinstance(datos.get('valor'), bool):
                mensajes.append(f'Valor debe ser un número (recibido: "{datos.get("valor")}")')
            else:
                try:
                    valor = _decimal(datos.get('valor'), 'Valor')
                except ValueError as e:
                    mensajes.append(str(e))
                else:
                    if valor == 0:
                        mensajes.append('Valor no puede ser cero')

            if mensajes:
                errores.append({'fila': idx, 'mensaje': '; '.join(mensajes)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break
                continue

            detalle = _texto_o_none(datos.get('detalle'))
            nuevos.append(ConConciliacionSoporte(
                conciliacion=conciliacion,
                fecha=fecha,
                debito=valor if valor > 0 else Decimal('0'),
                credito=-valor if valor < 0 else Decimal('0'),
                detalle=detalle[:DETALLE_MAX] if detalle else None,
            ))

        if errores:
            return 0, errores

        ConConciliacionSoporte.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []
