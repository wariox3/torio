from rest_framework import serializers

from contabilidad.models import ConCentroCosto
from general.models import GenSede


class GenSedeImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de sedes y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenSede
    nombre_archivo = 'sedes'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('codigo', 'Código'),
        ('centro_costo.id', 'Centro costo'),
    )
    campos_requeridos = {'nombre'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        Procesa todas las filas válidas en bulk:
          1. Pre-carga FKs en una query.
          2. Pre-carga duplicados en BD en una query.
          3. Valida cada fila contra mapas en memoria (sin BD).
          4. `bulk_create` al final si no hay errores.

        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs (ConCentroCosto) en un mapa {id: instancia}
        ids_centro = self._ids_int(filas_validas, 'centro_costo.id')
        mapa_centro = {o.id: o for o in ConCentroCosto.objects.filter(id__in=ids_centro)}

        # 2) Pre-cargar códigos existentes en BD para detectar duplicados
        codigos = {
            self._texto(datos.get('codigo'))
            for _, datos in filas_validas
            if self._texto(datos.get('codigo'))
        }
        ya_existen = set(
            GenSede.objects
            .filter(codigo__in=codigos)
            .values_list('codigo', flat=True)
        ) if codigos else set()

        # 3) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []
        vistos = set()  # códigos duplicados intra-archivo

        for idx, datos in filas_validas:
            try:
                centro_costo = self._fk_opcional(datos.get('centro_costo.id'), mapa_centro, 'Centro costo')

                codigo = self._texto_o_none(datos.get('codigo'))
                if codigo is not None:
                    if codigo in vistos:
                        raise ValueError(f'El código {codigo} está duplicado dentro del archivo')
                    vistos.add(codigo)
                    if codigo in ya_existen:
                        raise ValueError(f'Ya existe una sede con código {codigo}')

                nuevos.append(GenSede(
                    nombre=self._texto(datos.get('nombre')),
                    codigo=codigo,
                    centro_costo=centro_costo,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        # 4) Bulk create (solo si no hubo errores)
        if errores:
            return 0, errores

        if nuevos:
            GenSede.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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

    @staticmethod
    def _texto_o_none(v):
        if v is None or v == '':
            return None
        return str(v).strip()
