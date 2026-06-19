from rest_framework import serializers

from contabilidad.models import ConCuenta
from general.models import GenCuentaBanco, GenCuentaBancoClase, GenCuentaBancoTipo


class GenCuentaBancoImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de cuentas bancarias y la
    lógica de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenCuentaBanco
    nombre_archivo = 'cuentas_bancarias'

    campos_excel = (
        ('nombre', 'Nombre'),
        ('numero_cuenta', 'Número cuenta'),
        ('cuenta_banco_tipo.id', 'Cuenta banco tipo'),
        ('cuenta_banco_clase.id', 'Cuenta banco clase'),
        ('cuenta.id', 'Cuenta contable'),
    )
    campos_requeridos = {'nombre', 'cuenta_banco_tipo.id'}

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Pre-cargar FKs en mapas {id: instancia}
        mapa_tipo = {
            o.id: o for o in GenCuentaBancoTipo.objects.filter(
                id__in=self._ids_int(filas_validas, 'cuenta_banco_tipo.id'),
            )
        }
        mapa_clase = {
            o.id: o for o in GenCuentaBancoClase.objects.filter(
                id__in=self._ids_int(filas_validas, 'cuenta_banco_clase.id'),
            )
        }
        mapa_cuenta = {
            o.id: o for o in ConCuenta.objects.filter(
                id__in=self._ids_int(filas_validas, 'cuenta.id'),
            )
        }

        # 2) Construir instancias en memoria, recolectar errores
        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                nuevos.append(GenCuentaBanco(
                    nombre=self._texto(datos.get('nombre')),
                    numero_cuenta=self._texto_o_none(datos.get('numero_cuenta')),
                    cuenta_banco_tipo=self._fk_requerido(
                        datos.get('cuenta_banco_tipo.id'), mapa_tipo, 'Cuenta banco tipo',
                    ),
                    cuenta_banco_clase=self._fk_opcional(
                        datos.get('cuenta_banco_clase.id'), mapa_clase, 'Cuenta banco clase',
                    ),
                    cuenta=self._fk_opcional(datos.get('cuenta.id'), mapa_cuenta, 'Cuenta contable'),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            GenCuentaBanco.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
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
                pass  # tipos inválidos ya fueron filtrados en la fase 1
        return ids

    @staticmethod
    def _fk_requerido(valor, mapa, etiqueta):
        if valor in (None, ''):
            raise ValueError(f'{etiqueta} es obligatorio')
        return GenCuentaBancoImportarSerializer._fk_opcional(valor, mapa, etiqueta)

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
