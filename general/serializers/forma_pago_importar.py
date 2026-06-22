from rest_framework import serializers

from contabilidad.models import ConCuenta
from general.models import GenFormaPago


class GenFormaPagoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de formas de pago y la
    lógica de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenFormaPago
    nombre_archivo = 'formas_pago'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('cuenta.id', 'Cuenta'),
    )
    campos_requeridos = {'nombre'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # Pre-cargar la FK en un mapa {id: instancia} (una query)
        mapa_cuenta = self._mapa_fk(filas_validas, 'cuenta.id', ConCuenta)

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                cuenta = self._fk_opcional(datos.get('cuenta.id'), mapa_cuenta, 'Cuenta')
                nuevos.append(GenFormaPago(
                    nombre=self._texto(datos.get('nombre')),
                    cuenta=cuenta,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            GenFormaPago.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    def _mapa_fk(self, filas_validas, campo, modelo):
        """Pre-carga en un mapa {id: instancia} los registros referenciados por `campo`."""
        ids = self._ids_int(filas_validas, campo)
        if not ids:
            return {}
        return {o.id: o for o in modelo.objects.filter(id__in=ids)}

    @staticmethod
    def _ids_int(filas_validas, campo):
        """Extrae el conjunto de ids enteros para `campo` (ignora vacíos e inválidos)."""
        ids = set()
        for _, datos in filas_validas:
            valor = datos.get(campo)
            if valor in (None, ''):
                continue
            try:
                ids.add(int(valor))
            except (TypeError, ValueError):
                pass  # tipos inválidos se reportan al construir la fila
        return ids

    @staticmethod
    def _fk_opcional(valor, mapa, etiqueta):
        if valor in (None, ''):
            return None
        try:
            pk = int(valor)
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número (PK), recibido: "{valor}"')
        obj = mapa.get(pk)
        if obj is None:
            raise ValueError(f'{etiqueta} con id={pk} no existe')
        return obj

    @staticmethod
    def _texto(v):
        if v is None:
            return ''
        return str(v).strip()
