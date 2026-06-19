import datetime

from rest_framework import serializers

from general.models import GenResolucion


class GenResolucionImportarSerializer(serializers.Serializer):
    """
    Define la estructura del Excel de importación de resoluciones y la lógica
    de creación bulk.

    Es consumido por `ImportarExcelMixin` a través del atributo
    `serializer_class_importar` del ViewSet.

    Contrato esperado por el mixin:
        model:                clase del modelo
        campos_excel:         tuple[tuple[campo, encabezado], ...]
        campos_requeridos:    set[str]
        procesar_lote(filas)  -> (creados: int, errores: list[{fila, mensaje}])
    """

    model = GenResolucion
    nombre_archivo = 'resoluciones'

    campos_excel = (
        ('prefijo', 'Prefijo'),
        ('numero', 'Número'),
        ('clave_tecnica', 'Clave técnica'),
        ('set_prueba', 'Set prueba'),
        ('consecutivo_desde', 'Consecutivo desde'),
        ('consecutivo_hasta', 'Consecutivo hasta'),
        ('fecha_desde', 'Fecha desde'),
        ('fecha_hasta', 'Fecha hasta'),
        ('venta', 'Venta'),
        ('compra', 'Compra'),
    )
    campos_requeridos = {
        'consecutivo_desde', 'consecutivo_hasta', 'fecha_desde', 'fecha_hasta',
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

        errores = []
        nuevos = []

        for idx, datos in filas_validas:
            try:
                nuevos.append(GenResolucion(
                    prefijo=self._texto_o_none(datos.get('prefijo')),
                    numero=self._texto_o_none(datos.get('numero')),
                    clave_tecnica=self._texto_o_none(datos.get('clave_tecnica')),
                    set_prueba=self._texto_o_none(datos.get('set_prueba')),
                    consecutivo_desde=self._entero(datos.get('consecutivo_desde'), 'Consecutivo desde'),
                    consecutivo_hasta=self._entero(datos.get('consecutivo_hasta'), 'Consecutivo hasta'),
                    fecha_desde=self._fecha(datos.get('fecha_desde'), 'Fecha desde'),
                    fecha_hasta=self._fecha(datos.get('fecha_hasta'), 'Fecha hasta'),
                    venta=self._si_no(datos.get('venta')),
                    compra=self._si_no(datos.get('compra')),
                ))
            except Exception as e:
                errores.append({'fila': idx, 'mensaje': str(e)})
                if len(errores) >= self.LIMITE_ERRORES:
                    break

        if errores:
            return 0, errores

        if nuevos:
            GenResolucion.objects.bulk_create(nuevos, batch_size=self.BATCH_BULK_CREATE)
        return len(nuevos), []

    # ---- helpers ----

    @staticmethod
    def _texto_o_none(v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()

    @staticmethod
    def _entero(v, etiqueta):
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es obligatorio')
        try:
            return int(v)
        except (TypeError, ValueError):
            raise ValueError(f'{etiqueta} debe ser un número entero, recibido: "{v}"')

    @staticmethod
    def _si_no(v, defecto=False):
        if v is None or v == '':
            return defecto
        return str(v).strip().lower() in ('sí', 'si', 'true', '1', 'yes', 'verdadero')

    @staticmethod
    def _fecha(v, etiqueta):
        if isinstance(v, datetime.datetime):
            return v.date()
        if isinstance(v, datetime.date):
            return v
        if v is None or str(v).strip() == '':
            raise ValueError(f'{etiqueta} es obligatoria')
        texto = str(v).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return datetime.datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        raise ValueError(f'{etiqueta} con formato inválido: "{v}" (use AAAA-MM-DD)')
