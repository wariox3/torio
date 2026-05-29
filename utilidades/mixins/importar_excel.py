"""
Mixin para importar datos a un ViewSet desde un archivo .xlsx.
"""
from io import BytesIO
from zipfile import BadZipFile

from django.apps import apps
from django.db import models as dj_models, transaction
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from utilidades.throttles import ImportarUsuarioTenantThrottle

# Fuente cross-platform (Arial está en Windows/Mac y en Linux con msttcorefonts).
# El default de openpyxl es Calibri, que no viene en LibreOffice por defecto.
_FUENTE = 'Arial'
_FUENTE_TAM = 10
_FUENTE_NORMAL = Font(name=_FUENTE, size=_FUENTE_TAM)
_FUENTE_ENCABEZADO = Font(name=_FUENTE, size=_FUENTE_TAM, bold=True)


def _crear_workbook():
    wb = Workbook()
    wb._fonts[0] = _FUENTE_NORMAL
    return wb


_ImportarRequest = inline_serializer(
    name='ImportarRequest',
    fields={'archivo': serializers.FileField(help_text='Archivo .xlsx')},
)


class ImportarExcelMixin:
    """
    Agrega dos acciones al ViewSet:
        GET  /<recurso>/importar-ejemplo/  — descarga plantilla .xlsx
        POST /<recurso>/importar/          — sube archivo (multipart, campo `archivo`)

    Ambas exigen que el modelo asociado esté registrado en GenModelo con tipo='A'.

    El ViewSet que lo herede debe declarar:
        serializer_class_importar: Serializer
            Serializer que define la estructura del Excel y la lógica de creación.
            Debe exponer:
                model:        clase del modelo Django
                campos_excel: tuple[tuple[campo, encabezado], ...]
                procesar_fila(datos, fila)
                              # crea el registro o lanza Exception con mensaje.
                              # Si el registro ya existe debe lanzar error
                              # (el import solo crea, no actualiza).

    Si CUALQUIER fila falla, toda la transacción se revierte y se devuelve 400
    con la lista de errores. La respuesta exitosa es `{creados: N}`.

    Convención FK: campos con notación dotted (p.ej. `ciudad.id`) se marcan en la
    plantilla con sufijo `(ID)` y fondo amarillo para indicar al usuario que debe
    ingresar el identificador numérico del registro relacionado.
    """

    EXTENSIONES_VALIDAS_IMPORTAR = ('.xlsx',)
    LIMITE_ERRORES_IMPORTAR = 100
    MAX_FILAS_IMPORTAR = 10_000
    MAX_TAMANO_ARCHIVO_BYTES = 5 * 1024 * 1024  # 5 MB
    serializer_class_importar = None

    def get_serializer_importar(self):
        if self.serializer_class_importar is None:
            raise NotImplementedError(
                f"{type(self).__name__} debe declarar `serializer_class_importar`"
            )
        return self.serializer_class_importar()

    @staticmethod
    def _encabezado_importar(campo, encabezado, requeridos=()):
        sufijo = ''
        if '.' in campo:
            sufijo += ' (ID)'
        if campo in requeridos:
            sufijo += ' *'
        return f'{encabezado}{sufijo}'

    def _validar_administrador(self, modelo_cls):
        GenModelo = apps.get_model('general', 'GenModelo')
        gen_modelo = GenModelo.objects.filter(clase=modelo_cls.__name__).first()
        if gen_modelo is None:
            return Response(
                {'detail': f'El modelo {modelo_cls.__name__} no está registrado en GenModelo'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if gen_modelo.tipo != GenModelo.Tipo.ADMINISTRADOR:
            return Response(
                {'detail': 'Solo los modelos tipo administrador pueden importarse'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    @extend_schema(
        summary='Descargar plantilla de importación',
        description=(
            'Devuelve un archivo .xlsx con dos filas de ejemplo. Los campos FK se '
            'marcan con sufijo "(ID)" y fondo amarillo: deben rellenarse con el PK '
            'del registro relacionado.'
        ),
    )
    @action(detail=False, methods=['get'], url_path='importar-ejemplo')
    def importar_ejemplo(self, request):
        serializer = self.get_serializer_importar()
        modelo = serializer.model
        error = self._validar_administrador(modelo)
        if error:
            return error

        wb = _crear_workbook()
        ws = wb.active
        ws.title = 'Datos'

        campos = serializer.campos_excel
        requeridos = getattr(serializer, 'campos_requeridos', set())
        fondo_normal = PatternFill('solid', fgColor='D9D9D9')
        fondo_fk = PatternFill('solid', fgColor='FFF2CC')  # amarillo claro = campo FK
        for col, (campo, encabezado) in enumerate(campos, start=1):
            es_fk = '.' in campo
            texto = self._encabezado_importar(campo, encabezado, requeridos)
            celda = ws.cell(row=1, column=col, value=texto)
            celda.font = _FUENTE_ENCABEZADO
            celda.fill = fondo_fk if es_fk else fondo_normal
            ancho = max(len(str(texto)), 12)
            ws.column_dimensions[get_column_letter(col)].width = min(ancho + 2, 50)

        for fila in (1, 2):
            for col, (campo, _) in enumerate(campos, start=1):
                field = self._resolver_campo(modelo, campo)
                celda = ws.cell(row=fila + 1, column=col, value=self._valor_ejemplo(field, fila, campo))
                celda.font = _FUENTE_NORMAL

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        nombre = getattr(serializer, 'nombre_archivo', None) or modelo._meta.model_name
        response = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="importar_{nombre}_ejemplo.xlsx"'
        return response

    @staticmethod
    def _resolver_campo(modelo, dotted_path):
        partes = dotted_path.split('.')
        actual = modelo
        for parte in partes[:-1]:
            try:
                f = actual._meta.get_field(parte)
            except Exception:
                return None
            if not (f.is_relation and f.related_model):
                return None
            actual = f.related_model
        try:
            return actual._meta.get_field(partes[-1])
        except Exception:
            return None

    @staticmethod
    def _validar_tipo(field, valor, encabezado):
        """Devuelve mensaje de error si `valor` no coincide con el tipo del campo, sino None."""
        if field is None or valor in (None, ''):
            return None
        if isinstance(field, dj_models.BooleanField):
            if isinstance(valor, bool):
                return None
            if str(valor).strip().lower() in (
                'sí', 'si', 'no', 'true', 'false', '0', '1', 'yes', 'verdadero', 'falso',
            ):
                return None
            return f'{encabezado} debe ser Sí o No (recibido: "{valor}")'
        if isinstance(field, dj_models.DateField):
            import datetime as _dt
            if isinstance(valor, (_dt.date, _dt.datetime)):
                return None
            return f'{encabezado} debe ser una fecha (recibido: "{valor}")'
        if isinstance(field, dj_models.DecimalField):
            try:
                float(valor)
                return None
            except (TypeError, ValueError):
                return f'{encabezado} debe ser un número decimal (recibido: "{valor}")'
        if isinstance(field, (
            dj_models.BigIntegerField, dj_models.IntegerField,
            dj_models.SmallIntegerField, dj_models.PositiveIntegerField,
            dj_models.AutoField,
        )):
            try:
                int(valor)
                return None
            except (TypeError, ValueError):
                return f'{encabezado} debe ser un número entero (recibido: "{valor}")'
        return None  # CharField, TextField, etc. aceptan cualquier valor

    @staticmethod
    def _valor_ejemplo(field, fila, campo):
        if campo == 'id':
            return None
        if field is None:
            return f'ejemplo {fila}'
        if isinstance(field, dj_models.BooleanField):
            return 'Sí' if fila == 1 else 'No'
        if isinstance(field, dj_models.DateField):
            return '2026-01-15' if fila == 1 else '2026-12-31'
        if isinstance(field, dj_models.DecimalField):
            return 100 * fila
        if isinstance(field, (
            dj_models.BigIntegerField, dj_models.IntegerField,
            dj_models.SmallIntegerField, dj_models.PositiveIntegerField,
            dj_models.AutoField,
        )):
            return fila
        return f'ejemplo {fila}'

    @extend_schema(
        summary='Importar desde Excel',
        description=(
            'Recibe un archivo .xlsx en el campo `archivo` (multipart/form-data). '
            'La primera fila debe contener los encabezados de la plantilla. '
            'Procesamiento todo-o-nada: si alguna fila falla, no se guarda nada.'
        ),
        request={'multipart/form-data': _ImportarRequest},
    )
    @action(
        detail=False, methods=['post'],
        parser_classes=[MultiPartParser],
        throttle_classes=[ImportarUsuarioTenantThrottle],
    )
    def importar(self, request):
        serializer = self.get_serializer_importar()
        modelo = serializer.model
        error = self._validar_administrador(modelo)
        if error:
            return error

        archivo = request.FILES.get('archivo')
        if not archivo:
            return Response(
                {'detail': "Debe enviar el archivo en el campo 'archivo'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nombre = archivo.name.lower()
        if not any(nombre.endswith(ext) for ext in self.EXTENSIONES_VALIDAS_IMPORTAR):
            return Response(
                {
                    'detail': (
                        f"Extensión no permitida. Solo se aceptan: "
                        f"{', '.join(self.EXTENSIONES_VALIDAS_IMPORTAR)}"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if archivo.size > self.MAX_TAMANO_ARCHIVO_BYTES:
            mb = self.MAX_TAMANO_ARCHIVO_BYTES // (1024 * 1024)
            return Response(
                {'detail': f'El archivo supera el tamaño máximo permitido ({mb} MB)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # data_only=False permite detectar fórmulas vía cell.data_type == 'f'
            wb = load_workbook(archivo, data_only=False, read_only=True)
        except (InvalidFileException, BadZipFile):
            return Response(
                {'detail': 'El archivo no es un Excel válido o está corrupto'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {'detail': f'No se pudo leer el archivo: {e}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ws = wb.active
            rows = ws.iter_rows()  # cell objects (necesario para detectar fórmulas)

            try:
                header_row = next(rows)
            except StopIteration:
                return Response(
                    {'detail': 'El archivo no tiene contenido'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            headers_archivo = [c.value for c in header_row]

            campos = serializer.campos_excel
            requeridos = getattr(serializer, 'campos_requeridos', set())
            esperados = [self._encabezado_importar(c, e, requeridos) for c, e in campos]
            recibidos = [h for h in headers_archivo if h is not None]
            if recibidos != esperados:
                return Response(
                    {
                        'detail': 'Los encabezados del archivo no coinciden con la plantilla',
                        'esperados': esperados,
                        'recibidos': recibidos,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            mapping = {self._encabezado_importar(c, e, requeridos): c for c, e in campos}

            # ============ FASE 1: validación estructural (sin BD) ============
            # fórmulas, tipos de datos, campos requeridos.
            filas_validas = []
            errores_estructurales = []
            filas_procesadas = 0
            exceso_filas = False

            for idx, row in enumerate(rows, start=2):
                datos = {}
                formulas = []
                for col, header in enumerate(headers_archivo):
                    campo = mapping.get(header)
                    if not campo:
                        continue
                    celda = row[col] if col < len(row) else None
                    if celda is not None and celda.data_type == 'f':
                        formulas.append(header)
                        datos[campo] = None
                    else:
                        datos[campo] = celda.value if celda is not None else None

                if not any(v not in (None, '') for v in datos.values()) and not formulas:
                    continue
                filas_procesadas += 1

                if filas_procesadas > self.MAX_FILAS_IMPORTAR:
                    exceso_filas = True
                    break

                if formulas:
                    errores_estructurales.append({
                        'fila': idx,
                        'mensaje': f'Contiene fórmulas no permitidas en: {", ".join(formulas)}',
                    })
                    if len(errores_estructurales) >= self.LIMITE_ERRORES_IMPORTAR:
                        break
                    continue

                errores_tipo = []
                for campo, encabezado in campos:
                    msg = self._validar_tipo(
                        self._resolver_campo(modelo, campo),
                        datos.get(campo),
                        encabezado,
                    )
                    if msg:
                        errores_tipo.append(msg)
                if errores_tipo:
                    errores_estructurales.append({'fila': idx, 'mensaje': '; '.join(errores_tipo)})
                    if len(errores_estructurales) >= self.LIMITE_ERRORES_IMPORTAR:
                        break
                    continue

                faltantes = [
                    encabezado
                    for campo, encabezado in campos
                    if campo in requeridos and datos.get(campo) in (None, '')
                ]
                if faltantes:
                    errores_estructurales.append({
                        'fila': idx,
                        'mensaje': f'Faltan campos requeridos: {", ".join(faltantes)}',
                    })
                    if len(errores_estructurales) >= self.LIMITE_ERRORES_IMPORTAR:
                        break
                    continue

                filas_validas.append((idx, datos))
        finally:
            wb.close()

        if exceso_filas:
            return Response(
                {'detail': f'El archivo supera el máximo de {self.MAX_FILAS_IMPORTAR} filas permitidas'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if filas_procesadas == 0:
            return Response(
                {'detail': 'El archivo no tiene filas para importar'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if errores_estructurales:
            return self._respuesta_errores_importar('estructural', errores_estructurales)

        # ============ FASE 2: lógica de negocio + creación (transaccional) ============
        # El serializer procesa el lote completo: pre-carga FKs, valida, bulk_create.
        with transaction.atomic():
            creados, errores_negocio = serializer.procesar_lote(filas_validas)
            if errores_negocio:
                transaction.set_rollback(True)

        if errores_negocio:
            return self._respuesta_errores_importar('negocio', errores_negocio)

        return Response({'creados': creados})

    def _respuesta_errores_importar(self, fase, errores):
        limite_alcanzado = len(errores) >= self.LIMITE_ERRORES_IMPORTAR
        if limite_alcanzado:
            detail = (
                f'Se detectaron al menos {self.LIMITE_ERRORES_IMPORTAR} errores en la fase '
                f'{fase}. Se detuvo la validación. No se importó nada — corrija y reintente.'
            )
        elif fase == 'estructural':
            detail = (
                'El archivo tiene problemas estructurales (fórmulas, tipos o requeridos). '
                'No se procesó ningún registro.'
            )
        else:
            detail = (
                'Errores de datos al intentar guardar (FK inexistente, duplicados, etc.). '
                'No se importó nada.'
            )
        return Response(
            {
                'detail': detail,
                'fase': fase,
                'total_errores': len(errores),
                'errores': errores,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
