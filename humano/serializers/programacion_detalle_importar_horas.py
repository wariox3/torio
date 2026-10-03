"""
Importación de horas sobre los detalles de una programación.

No sigue el contrato plano de los otros importadores, por dos razones:

  * **Actualiza, no crea.** Los detalles ya existen (los creó `cargar-contrato`):
    cada fila trae el `ID` de un detalle y sus horas. Lo que el mixin reporta como
    `creados` son los detalles actualizados.
  * **El padre lo fija el front, nunca el Excel.** El ViewSet recibe
    `programacion_id`, la valida y construye este serializer con ella; un `ID` de
    otra programación es un error de la fila.

Las columnas `Identificación` y `Nombre` solo están para que el usuario sepa de
quién es cada fila: la plantilla las trae llenas y al importar se ignoran.
"""
from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from humano.models import HumProgramacion, HumProgramacionDetalle
from humano.models.programacion_detalle import MENSAJE_PROGRAMACION_CERRADA

CAMPOS_HORAS = (
    ('diurna', 'Diurna'),
    ('nocturna', 'Nocturna'),
    ('festiva_diurna', 'Festiva diurna'),
    ('festiva_nocturna', 'Festiva nocturna'),
    ('extra_diurna', 'Extra diurna'),
    ('extra_nocturna', 'Extra nocturna'),
    ('extra_festiva_diurna', 'Extra festiva diurna'),
    ('extra_festiva_nocturna', 'Extra festiva nocturna'),
    ('recargo_nocturno', 'Recargo nocturno'),
    ('recargo_festivo_diurno', 'Recargo festivo diurno'),
    ('recargo_festivo_nocturno', 'Recargo festivo nocturno'),
)

# Los campos de horas son `DecimalField(max_digits=10, decimal_places=3)`.
_HORAS_MAXIMO = Decimal('9999999.999')
_TRES_DECIMALES = Decimal('0.001')


class HumProgramacionDetalleImportarHorasSerializer(serializers.Serializer):
    """
    Es consumido por `ImportarExcelMixin`, construido con la programación padre
    (ver `HumProgramacionDetalleViewSet`).

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (actualizados: int, errores: list[{fila, mensaje}])
    """

    model = HumProgramacionDetalle

    # `identificacion` y `nombre` no son campos del modelo: el mixin no les valida
    # tipo y `procesar_lote` no los lee.
    campos_excel = (
        ('id', 'ID'),
        ('identificacion', 'Identificación'),
        ('nombre', 'Nombre'),
        *CAMPOS_HORAS,
    )
    campos_requeridos = {'id'}

    # El archivo sale de la plantilla con todos los empleados: que el usuario vea
    # de una vez los errores de tipo y los de datos.
    errores_completos = True

    LIMITE_ERRORES = 100

    def __init__(self, programacion, **kwargs):
        super().__init__(**kwargs)
        self.programacion = programacion
        self.nombre_archivo = f'programacion_{programacion.id}_horas'

    def procesar_lote(self, filas_validas):
        """
        Corre dentro del `transaction.atomic()` del mixin, que revierte todo si se
        devuelve algún error.
        """
        if not filas_validas:
            return 0, []

        # La programación se relee bloqueada: entre validarla en el ViewSet y llegar
        # acá pudo generarse en otra petición.
        try:
            programacion = HumProgramacion.objects.select_for_update().get(pk=self.programacion.pk)
        except HumProgramacion.DoesNotExist:
            return 0, [{'mensaje': 'La programación ya no existe.'}]
        if programacion.estado_generado or programacion.estado_aprobado:
            return 0, [{'mensaje': MENSAJE_PROGRAMACION_CERRADA}]

        ids = set()
        for _, datos in filas_validas:
            try:
                ids.add(int(datos['id']))
            except (TypeError, ValueError):
                pass
        detalles = {
            d.id: d
            for d in HumProgramacionDetalle.objects.filter(programacion=programacion, id__in=ids)
        }

        errores = []
        vistos = {}
        actualizar = []
        for idx, datos in filas_validas:
            mensajes = []
            pk = int(datos['id'])
            detalle = detalles.get(pk)
            if detalle is None:
                mensajes.append(f'El detalle {pk} no pertenece a la programación {programacion.id}.')
            elif pk in vistos:
                mensajes.append(f'El detalle {pk} ya viene en la fila {vistos[pk]}.')
            else:
                vistos[pk] = idx

            horas = {}
            for campo, encabezado in CAMPOS_HORAS:
                try:
                    horas[campo] = self._horas(datos.get(campo), encabezado)
                except ValueError as e:
                    mensajes.append(str(e))

            if mensajes:
                # Uno por problema, aunque la fila se repita: así el usuario ve de
                # una vez todo lo que tiene que arreglar en esa línea.
                errores.extend({'fila': idx, 'mensaje': m} for m in mensajes)
                if len(errores) >= self.LIMITE_ERRORES:
                    break
                continue

            for campo, valor in horas.items():
                setattr(detalle, campo, valor)
            actualizar.append(detalle)

        if errores:
            return 0, errores[:self.LIMITE_ERRORES]

        HumProgramacionDetalle.objects.bulk_update(actualizar, [campo for campo, _ in CAMPOS_HORAS])
        return len(actualizar), []

    @staticmethod
    def _horas(valor, encabezado):
        """Una celda vacía es cero horas: así queda la columna al borrar su valor."""
        if valor is None or str(valor).strip() == '':
            return Decimal(0)
        try:
            horas = Decimal(str(valor).strip()).quantize(_TRES_DECIMALES)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f'{encabezado} debe ser un número (recibido: "{valor}")')
        if horas < 0:
            raise ValueError(f'{encabezado} no puede ser negativo (recibido: {valor})')
        if horas > _HORAS_MAXIMO:
            raise ValueError(f'{encabezado} excede el máximo permitido (recibido: {valor})')
        return horas
