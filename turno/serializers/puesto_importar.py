from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from contabilidad.models import ConCentroCosto
from general.models import GenCiudad, GenContacto
from turno.models import TurProgramador, TurPuesto


class TurPuestoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de puestos y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = TurPuesto
    nombre_archivo = 'puestos'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('direccion', 'Dirección'),
        ('celular', 'Celular'),
        ('contacto.id', 'Contacto'),
        ('programador.id', 'Programador'),
        ('ciudad.id', 'Ciudad'),
        ('centro_costo.id', 'Centro de costo'),
        ('latitud', 'Latitud'),
        ('longitud', 'Longitud'),
        ('estado_inactivo', 'Inactivo'),
        ('comentario', 'Comentario'),
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

        # 1) Pre-cargar FKs de cada catálogo en mapas {id: instancia}
        mapa_contacto = self._mapa_fk(filas_validas, 'contacto.id', GenContacto)
        mapa_programador = self._mapa_fk(filas_validas, 'programador.id', TurProgramador)
        mapa_ciudad = self._mapa_fk(filas_validas, 'ciudad.id', GenCiudad)
        mapa_centro_costo = self._mapa_fk(filas_validas, 'centro_costo.id', ConCentroCosto)

        # 2) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                contacto = self._fk_opcional(datos.get('contacto.id'), mapa_contacto, 'Contacto')
                programador = self._fk_opcional(datos.get('programador.id'), mapa_programador, 'Programador')
                ciudad = self._fk_opcional(datos.get('ciudad.id'), mapa_ciudad, 'Ciudad')
                centro_costo = self._fk_opcional(datos.get('centro_costo.id'), mapa_centro_costo, 'Centro de costo')

                nuevos.append(TurPuesto(
                    nombre=self._texto(datos.get('nombre')),
                    direccion=self._texto_o_none(datos.get('direccion')),
                    celular=self._texto_o_none(datos.get('celular')),
                    latitud=self._decimal_o_none(datos.get('latitud'), 'Latitud'),
                    longitud=self._decimal_o_none(datos.get('longitud'), 'Longitud'),
                    comentario=self._texto_o_none(datos.get('comentario')),
                    estado_inactivo=self._si_no(datos.get('estado_inactivo')),
                    contacto=contacto,
                    programador=programador,
                    ciudad=ciudad,
                    centro_costo=centro_costo,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            TurPuesto.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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

    @staticmethod
    def _texto_o_none(v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()

    @staticmethod
    def _decimal_o_none(v, etiqueta):
        if v is None or str(v).strip() == '':
            return None
        try:
            return Decimal(str(v).strip())
        except (InvalidOperation, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número, recibido: "{v}"')

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
