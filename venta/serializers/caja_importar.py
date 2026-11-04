from rest_framework import serializers

from general.models import GenSede
from venta.models import VenCaja


class VenCajaImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de cajas y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])

    Las cajas importadas quedan activas: `estado_activo` no va en el Excel.
    """

    model = VenCaja
    nombre_archivo = 'cajas'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('placa', 'Placa'),
        ('ubicacion', 'Ubicación'),
        ('tipo', 'Tipo'),
        ('sede.id', 'Sede'),
    )
    campos_requeridos = {'nombre', 'sede.id'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        ids_sede = self._ids_int(filas_validas, 'sede.id')
        mapa_sede = {o.id: o for o in GenSede.objects.filter(id__in=ids_sede)}

        # La caja no tiene código: dentro de una sede el nombre es lo que la
        # identifica, así que el par (sede, nombre) se usa como clave natural
        # para rechazar repetidos (el import solo crea, no actualiza).
        ya_existen = set(
            VenCaja.objects
            .filter(sede_id__in=ids_sede)
            .values_list('sede_id', 'nombre')
        ) if ids_sede else set()

        errores = []
        nuevos = []
        vistos = set()  # pares (sede, nombre) duplicados intra-archivo

        for idx, datos in filas_validas:
            try:
                sede = self._fk_requerida(datos.get('sede.id'), mapa_sede, 'Sede')
                nombre = self._texto(datos.get('nombre'))

                clave = (sede.id, nombre)
                if clave in vistos:
                    raise ValueError(f'La caja {nombre} de la sede {sede.nombre} está duplicada dentro del archivo')
                vistos.add(clave)
                if clave in ya_existen:
                    raise ValueError(f'Ya existe una caja con nombre {nombre} en la sede {sede.nombre}')

                nuevos.append(VenCaja(
                    nombre=nombre,
                    placa=self._texto_o_none(datos.get('placa')),
                    ubicacion=self._texto_o_none(datos.get('ubicacion')),
                    tipo=self._texto_o_none(datos.get('tipo')),
                    sede=sede,
                ))
            except Exception as e:  # noqa: BLE001 — el error de la fila se reporta al usuario
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            VenCaja.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

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
                pass
        return ids

    @staticmethod
    def _fk_requerida(valor, mapa, etiqueta):
        if valor in (None, ''):
            raise ValueError(f'{etiqueta} es obligatoria')
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

    @staticmethod
    def _texto_o_none(v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()
