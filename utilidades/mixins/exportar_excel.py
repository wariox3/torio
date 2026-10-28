"""
Mixin para exportar datos de un ViewSet a un archivo .xlsx.
"""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from rest_framework.decorators import action

from utilidades.filtros import aplicar_filtros, aplicar_ordenamientos
from utilidades.formatos import configuracion_actual, datos_empresa
from utilidades.mixins.filtros import BusquedaRequest

# Fuente cross-platform (Arial está en Windows/Mac y en Linux con msttcorefonts).
# El default de openpyxl es Calibri, que no viene en LibreOffice por defecto.
_FUENTE = 'Arial'
_FUENTE_TAM = 10
_FUENTE_NORMAL = Font(name=_FUENTE, size=_FUENTE_TAM)
# Colores de RedDoc: el azul de la marca (#009EF7) aclarado para el fondo de los
# encabezados, y el azul marino de la marca para sus textos.
_AZUL_MARINO = '13263C'
_FONDO_ENCABEZADO = PatternFill('solid', fgColor='CCECFD')
_FUENTE_ENCABEZADO = Font(name=_FUENTE, size=_FUENTE_TAM, bold=True, color=_AZUL_MARINO)
_FUENTE_TITULO = Font(name=_FUENTE, size=14, bold=True, color=_AZUL_MARINO)
_FUENTE_EMPRESA = Font(name=_FUENTE, size=12, bold=True, color=_AZUL_MARINO)
_FUENTE_GENERADO = Font(name=_FUENTE, size=9, color='808080')
_CENTRADO = Alignment(horizontal='center', vertical='center')

# Con título, la tabla arranca debajo de las tres filas del bloque.
_FILAS_TITULO = 3

# Límites del ancho automático, en caracteres: una columna vacía no queda como
# una raya, y un texto muy largo (un comentario) no estira la hoja sin fin.
_ANCHO_MINIMO = 8
_ANCHO_MAXIMO = 60


def _largo(valor):
    """
    Cuántos caracteres ocupa el valor en la celda, para el ancho de su columna.

    Un `Decimal` se mide como se lee, con separador de miles y dos decimales:
    `str()` daría los seis decimales del modelo y la columna saldría el doble de
    ancha. Una fecha, como AAAA-MM-DD.
    """
    if valor is None:
        return 0
    if isinstance(valor, (Decimal, float)):
        return len(f'{valor:,.2f}')
    if isinstance(valor, datetime):
        return 16
    if isinstance(valor, date):
        return 10
    return max((len(linea) for linea in str(valor).splitlines()), default=0)


def _crear_workbook():
    wb = Workbook()
    wb._fonts[0] = _FUENTE_NORMAL
    return wb


class ExportarExcelMixin:
    """
    Agrega la acción `POST /<recurso>/excel/` que devuelve un archivo .xlsx
    con los datos filtrados (mismos filtros/ordenamientos que `lista`, sin paginar).

    El ViewSet que lo herede debe declarar:
        serializer_class_exportar: Serializer
            Serializer que define la estructura del Excel. Debe exponer:
                model:          clase del modelo Django
                campos_excel:   tuple[tuple[campo, encabezado], ...]
                valor_excel(obj, campo) -> Any
                nombre_archivo: str (opcional; default = nombre del modelo)
                hoja:           str (opcional; default = 'Datos')
                titulo:         str (opcional; ver `get_titulo_excel`)

    Con título, encima de la tabla van tres filas combinadas a lo ancho de las
    columnas: el título, la empresa con su NIT y cuándo se generó con cuántos
    registros. Sin título la tabla arranca en la fila 1, como siempre: los
    exportar de los maestros se usan de base para importar, y el importar lee
    los encabezados de la fila 1.
    """

    serializer_class_exportar = None

    def get_serializer_exportar(self):
        if self.serializer_class_exportar is None:
            raise NotImplementedError(
                f"{type(self).__name__} debe declarar `serializer_class_exportar`"
            )
        return self.serializer_class_exportar()

    def get_titulo_excel(self, serializer):
        """El título del Excel, o `None` para la tabla sola. Los informes lo toman de su registro."""
        return getattr(serializer, 'titulo', None)

    def get_queryset_excel(self):
        if hasattr(self, 'get_queryset_lista'):
            return self.get_queryset_lista()
        return self.get_queryset()

    def _config_lista(self, name, default):
        """Lee config (campos_filtrables, ordenamiento_default_lista) del serializer principal o del viewset."""
        serializer_cls = self.get_serializer_class()
        if hasattr(serializer_cls, name):
            return getattr(serializer_cls, name)
        return getattr(self, name, default)

    @extend_schema(
        summary='Exportar a Excel',
        description=(
            'Devuelve un archivo .xlsx con los registros filtrados. '
            'Acepta los mismos `filtros` y `ordenamientos` que la acción `lista`.'
        ),
        request=BusquedaRequest,
        responses={
            (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): bytes,
        },
    )
    @action(detail=False, methods=['post'])
    def excel(self, request):
        serializer = self.get_serializer_exportar()
        filtros = request.data.get('filtros') or []
        ordenamientos = request.data.get('ordenamientos') or []

        qs = self.get_queryset_excel()
        campos_filtrables = self._config_lista('campos_filtrables', set())
        qs = aplicar_filtros(qs, filtros, campos_filtrables)
        qs = aplicar_ordenamientos(qs, ordenamientos, campos_filtrables)
        if not ordenamientos:
            default = self._config_lista('ordenamiento_default_lista', ())
            if default:
                qs = qs.order_by(*default)

        wb = _crear_workbook()
        ws = wb.active
        ws.title = getattr(serializer, 'hoja', None) or 'Datos'

        campos = serializer.campos_excel
        titulo = self.get_titulo_excel(serializer)
        fila_encabezados = _FILAS_TITULO + 1 if titulo else 1

        # El ancho de cada columna se ajusta a su contenido: se mide al escribir.
        anchos = [_largo(encabezado) for _, encabezado in campos]
        for col, (_, encabezado) in enumerate(campos, start=1):
            celda = ws.cell(row=fila_encabezados, column=col, value=encabezado)
            celda.font = _FUENTE_ENCABEZADO
            celda.fill = _FONDO_ENCABEZADO

        # chunk_size es obligatorio en .iterator() cuando el queryset trae
        # prefetch_related (Django lo exige para acotar la memoria de los prefetch).
        registros = 0
        for fila, obj in enumerate(qs.iterator(chunk_size=2000), start=fila_encabezados + 1):
            registros += 1
            for col, (campo, _) in enumerate(campos, start=1):
                valor = serializer.valor_excel(obj, campo)
                celda = ws.cell(row=fila, column=col, value=valor)
                celda.font = _FUENTE_NORMAL
                anchos[col - 1] = max(anchos[col - 1], _largo(valor))

        if titulo:
            # Va al final porque la tercera fila lleva la cantidad de registros,
            # que se cuenta al escribirlos: así no se hace un `count()` aparte.
            self._escribir_titulo(ws, titulo, len(campos), registros)

        # El título no cuenta: va combinado sobre todas las columnas.
        for col, ancho in enumerate(anchos, start=1):
            ws.column_dimensions[get_column_letter(col)].width = min(max(ancho, _ANCHO_MINIMO) + 2, _ANCHO_MAXIMO)

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        nombre = getattr(serializer, 'nombre_archivo', None) or qs.model._meta.model_name
        response = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{nombre}.xlsx"'
        return response

    @staticmethod
    def _escribir_titulo(ws, titulo, columnas, registros):
        """Las tres filas del bloque, cada una combinada a lo ancho de la tabla."""
        empresa = datos_empresa(configuracion_actual())
        nit = f'NIT {empresa["nit"]}' if empresa['nit'] else ''
        generado = timezone.localtime().strftime('%Y/%m/%d %H:%M')
        filas = (
            (titulo, _FUENTE_TITULO),
            (' · '.join(parte for parte in (empresa['razon_social'], nit) if parte), _FUENTE_EMPRESA),
            (f'Generado: {generado} · {registros} registro{"" if registros == 1 else "s"}', _FUENTE_GENERADO),
        )
        for numero, (texto, fuente) in enumerate(filas, start=1):
            celda = ws.cell(row=numero, column=1, value=texto)
            celda.font = fuente
            celda.alignment = _CENTRADO
            if columnas > 1:
                ws.merge_cells(start_row=numero, start_column=1, end_row=numero, end_column=columnas)
        ws.row_dimensions[1].height = 22
