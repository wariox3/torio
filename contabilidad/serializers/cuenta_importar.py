from rest_framework import serializers

from contabilidad.models import (
    ConCuenta,
    ConCuentaClase,
    ConCuentaCuenta,
    ConCuentaGrupo,
    ConCuentaSubcuenta,
)


class ConCuentaImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de cuentas y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = ConCuenta
    nombre_archivo = 'cuentas'

    campos_excel = (
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('exige_base', 'Exige base'),
        ('exige_contacto', 'Exige contacto'),
        ('exige_grupo', 'Exige grupo'),
        ('permite_movimiento', 'Permite movimiento'),
        ('nivel', 'Nivel'),
        ('cuenta_clase.id', 'Clase'),
        ('cuenta_grupo.id', 'Grupo'),
        ('cuenta_cuenta.id', 'Cuenta'),
        ('cuenta_subcuenta.id', 'Subcuenta'),
    )
    campos_requeridos = {'nombre'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        Procesa todas las filas válidas en bulk:
          1. Pre-carga FKs (una query por catálogo).
          2. Valida cada fila contra mapas en memoria (sin BD).
          3. `bulk_create` al final si no hay errores.

        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs de cada catálogo en mapas {id: instancia}
        mapa_clase = self._mapa_fk(filas_validas, 'cuenta_clase.id', ConCuentaClase)
        mapa_grupo = self._mapa_fk(filas_validas, 'cuenta_grupo.id', ConCuentaGrupo)
        mapa_cuenta = self._mapa_fk(filas_validas, 'cuenta_cuenta.id', ConCuentaCuenta)
        mapa_subcuenta = self._mapa_fk(filas_validas, 'cuenta_subcuenta.id', ConCuentaSubcuenta)

        # 2) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                cuenta_clase = self._fk_opcional(datos.get('cuenta_clase.id'), mapa_clase, 'Clase')
                cuenta_grupo = self._fk_opcional(datos.get('cuenta_grupo.id'), mapa_grupo, 'Grupo')
                cuenta_cuenta = self._fk_opcional(datos.get('cuenta_cuenta.id'), mapa_cuenta, 'Cuenta')
                cuenta_subcuenta = self._fk_opcional(
                    datos.get('cuenta_subcuenta.id'), mapa_subcuenta, 'Subcuenta',
                )

                nuevos.append(ConCuenta(
                    codigo=self._texto(datos.get('codigo')) or '0',
                    nombre=self._texto(datos.get('nombre')),
                    exige_base=self._si_no(datos.get('exige_base')),
                    exige_contacto=self._si_no(datos.get('exige_contacto')),
                    exige_grupo=self._si_no(datos.get('exige_grupo')),
                    permite_movimiento=self._si_no(datos.get('permite_movimiento')),
                    nivel=self._entero_o_none(datos.get('nivel')),
                    cuenta_clase=cuenta_clase,
                    cuenta_grupo=cuenta_grupo,
                    cuenta_cuenta=cuenta_cuenta,
                    cuenta_subcuenta=cuenta_subcuenta,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        # 3) Bulk create (solo si no hubo errores)
        if errores:
            return 0, errores

        if nuevos:
            ConCuenta.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
    def _entero_o_none(v):
        if v in (None, ''):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
