from rest_framework import serializers

from contabilidad.models import ConCuenta
from contabilidad.servicios import cuenta as reglas


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

    `nivel` y los catálogos NO se importan: se derivan del `codigo` con las mismas
    reglas que crear (`contabilidad.servicios.cuenta`). El padre de una auxiliar
    puede venir en el mismo archivo; si viene, se guarda sin movimiento.
    """

    model = ConCuenta
    nombre_archivo = 'cuentas'

    campos_excel = (
        ('codigo', 'Código'),
        ('nombre', 'Nombre'),
        ('exige_base', 'Exige base'),
        ('exige_contacto', 'Exige contacto'),
        ('exige_centro_costo', 'Exige centro de costo'),
        ('permite_movimiento', 'Permite movimiento'),
    )
    campos_requeridos = {'codigo', 'nombre'}
    valores_ejemplo = {
        'codigo': ('110505', '11050501'),
        'nombre': ('Caja general', 'Caja general sede norte'),
        'permite_movimiento': ('No', 'Sí'),
    }

    LIMITE_ERRORES = 100
    BATCH_BULK_CREATE = 500

    def procesar_lote(self, filas_validas):
        """
        filas_validas: list[(idx, datos)]
        Retorna: (creados, errores)
        """
        if not filas_validas:
            return 0, []

        # 1) Formato, sin BD: lo demás solo se consulta para los códigos bien formados.
        errores = []
        filas = []  # [(idx, datos, codigo)]
        for idx, datos in filas_validas:
            codigo = reglas.normalizar_codigo(datos.get('codigo'))
            try:
                reglas.validar_formato(codigo)
            except reglas.CuentaInvalida as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    return 0, errores
                continue
            filas.append((idx, datos, codigo))

        # 2) Precargas: catálogos, códigos ya existentes y padres (una query cada uno,
        #    más una por FK hacia ConCuenta para saber qué padres se usan).
        codigos = {codigo for _, _, codigo in filas}
        catalogos = reglas.cargar_catalogos(codigos)
        ya_existen = set(
            ConCuenta.objects.filter(codigo__in=codigos).values_list('codigo', flat=True)
        )
        codigos_padre = {reglas.codigo_padre(c) for c in codigos} - {None}
        padres_bd = {
            p.codigo: p for p in ConCuenta.objects.filter(codigo__in=codigos_padre)
        }
        usos_padres = reglas.usos(p.pk for p in padres_bd.values() if p.permite_movimiento)

        nuevos = {}  # codigo → ConCuenta
        padres_a_apagar = set()
        for idx, datos, codigo in filas:
            try:
                if codigo in nuevos:
                    raise reglas.CuentaInvalida(f'El código {codigo} está duplicado dentro del archivo')
                if codigo in ya_existen:
                    raise reglas.CuentaInvalida(f'Ya existe una cuenta con código {codigo}')

                derivados = reglas.derivar(codigo, catalogos)

                codigo_padre = reglas.codigo_padre(codigo)
                if codigo_padre:
                    padre = padres_bd.get(codigo_padre)
                    if padre is not None:
                        reglas.validar_padre(padre, codigo, usos_padres.get(padre.pk, []))
                        padres_a_apagar.add(padre.pk)
                    elif codigo_padre not in codigos:
                        raise reglas.CuentaInvalida(reglas.mensaje_padre_inexistente(codigo))

                nuevos[codigo] = ConCuenta(
                    codigo=codigo,
                    nombre=self._texto(datos.get('nombre')),
                    exige_base=self._si_no(datos.get('exige_base')),
                    exige_contacto=self._si_no(datos.get('exige_contacto')),
                    exige_centro_costo=self._si_no(datos.get('exige_centro_costo')),
                    permite_movimiento=self._si_no(datos.get('permite_movimiento')),
                    **derivados,
                )
            except reglas.CuentaInvalida as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            # Los de formato (paso 1) van antes que los demás: se devuelven por fila.
            return 0, sorted(errores, key=lambda e: e['fila'])

        # Solo las hojas mueven: un padre que viene en el archivo junto a su auxiliar
        # se guarda sin movimiento, como se apaga el que ya estaba en la BD.
        for codigo in codigos_padre & nuevos.keys():
            nuevos[codigo].permite_movimiento = False

        ConCuenta.objects.bulk_create(nuevos.values(), batch_size=self.BATCH_BULK_CREATE)
        reglas.apagar_movimiento(padres_a_apagar)
        return len(nuevos), []

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
