from rest_framework import serializers

from contabilidad.models import (
    ConCuenta,
    ConCuentaClase,
    ConCuentaCuenta,
    ConCuentaGrupo,
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

    `nivel`, `cuenta_clase`, `cuenta_grupo` y `cuenta_cuenta` NO se importan:
    se derivan automáticamente del `codigo` (ver `_derivar`).
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

        # 1) Precargar los PKs existentes de cada catálogo (una query por catálogo).
        clases = set(ConCuentaClase.objects.values_list('id', flat=True))
        grupos = set(ConCuentaGrupo.objects.values_list('id', flat=True))
        cuentas = set(ConCuentaCuenta.objects.values_list('id', flat=True))

        # 2) Precargar códigos existentes en BD para detectar duplicados (codigo es unique)
        codigos = {self._texto(datos.get('codigo')) or '0' for _, datos in filas_validas}
        ya_existen = set(
            ConCuenta.objects
            .filter(codigo__in=codigos)
            .values_list('codigo', flat=True)
        ) if codigos else set()

        errores = []
        nuevos = []
        vistos = set()  # códigos duplicados intra-archivo

        for idx, datos in filas_validas:
            try:
                codigo = self._texto(datos.get('codigo')) or '0'

                if codigo in vistos:
                    raise ValueError(f'El código {codigo} está duplicado dentro del archivo')
                vistos.add(codigo)
                if codigo in ya_existen:
                    raise ValueError(f'Ya existe una cuenta con código {codigo}')

                clase_id, grupo_id, cuenta_id, nivel = self._derivar(codigo)

                nuevos.append(ConCuenta(
                    codigo=codigo,
                    nombre=self._texto(datos.get('nombre')),
                    exige_base=self._si_no(datos.get('exige_base')),
                    exige_contacto=self._si_no(datos.get('exige_contacto')),
                    exige_grupo=self._si_no(datos.get('exige_grupo')),
                    permite_movimiento=self._si_no(datos.get('permite_movimiento')),
                    nivel=nivel,
                    # Si el prefijo derivado no existe en el catálogo, se deja en null.
                    cuenta_clase_id=clase_id if clase_id in clases else None,
                    cuenta_grupo_id=grupo_id if grupo_id in grupos else None,
                    cuenta_cuenta_id=cuenta_id if cuenta_id in cuentas else None,
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            ConCuenta.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- lógica de negocio ----

    @staticmethod
    def _derivar(codigo):
        """
        Deriva (cuenta_clase_id, cuenta_grupo_id, cuenta_cuenta_id, nivel) a partir
        del prefijo del código. Los catálogos usan el prefijo numérico como PK.
        """
        longitud = len(codigo)
        clase_id = int(codigo[0]) if longitud >= 1 else None
        grupo_id = int(codigo[:2]) if longitud >= 2 else None
        cuenta_id = int(codigo[:4]) if longitud >= 4 else None
        # subcuenta_id = int(codigo[:6]) if longitud >= 6 else None

        if longitud <= 1:
            nivel = 1
        elif longitud == 2:
            nivel = 2
        elif longitud <= 4:
            nivel = 3
        elif longitud <= 6:
            nivel = 4
        else:
            nivel = 5

        return clase_id, grupo_id, cuenta_id, nivel

    # ---- helpers ----

    @staticmethod
    def _texto(v):
        if v is None:
            return ''
        return str(v).strip()

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')
