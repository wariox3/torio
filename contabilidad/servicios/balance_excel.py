"""
Excel de los informes de contabilidad.

No usa `ExportarExcelMixin`: el mixin escribe una tabla plana que arranca en la
fila de encabezados, y estos informes llevan encima un bloque con la empresa y el
corte, más un formato de número por columna. El mixin sigue sirviendo para todo
lo demás; generalizarlo para este caso lo convertiría en un motor de reportes.
"""
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from contabilidad.servicios import estado_resultados as er
from contabilidad.servicios import situacion_financiera as sf

_FUENTE = 'Arial'
_FONDO = PatternFill('solid', fgColor='9CDFEB')

IMPORTE = '#,##0.00'
FECHA = 'yyyy-mm-dd'
TEXTO = 'General'

_FILA_ENCABEZADOS = 7

# (campo de la fila, encabezado, formato). El ancho no se declara: se calcula del
# contenido al escribir, como hacía itrio, así una razón social larga o un nombre
# de cuenta largo no quedan cortados en un tenant y sobrados en otro.
_CUENTA = (
    ('tipo', 'Tipo', TEXTO),
    ('codigo', 'Cuenta', TEXTO),
)
_CONTACTO = (
    ('nombre', 'Nombre Cuenta', TEXTO),
    ('identificacion', 'Identificación', TEXTO),
    ('contacto', 'Contacto', TEXTO),
)
_ASIENTO = (
    ('comprobante', 'Comprobante', TEXTO),
    ('numero', 'Numero', TEXTO),
    ('fecha', 'Fecha', FECHA),
)
_SALDOS = (
    ('saldo_anterior', 'Saldo anterior ($)', IMPORTE),
    ('debito', 'Debitos ($)', IMPORTE),
    ('credito', 'Creditos ($)', IMPORTE),
    ('saldo_final', 'Saldo actual ($)', IMPORTE),
)

# Una forma de tabla por informe. El encabezado de la columna del nombre cambia
# entre las dos familias —«Nombre de cuenta» en las de cuenta sola, «Nombre
# Cuenta» en las que abren por contacto—, así que las columnas se declaran
# enteras y no por composición ciega.
BALANCE = {
    'titulo': 'Balance de prueba',
    'hoja': 'balance_prueba',
    'columnas': _CUENTA + (('nombre', 'Nombre de cuenta', TEXTO),) + _SALDOS,
}
BALANCE_CONTACTO = {
    'titulo': 'Balance de prueba por contacto',
    'hoja': 'balance_prueba_contacto',
    'columnas': _CUENTA + _CONTACTO + _SALDOS,
}
AUXILIAR_CUENTA = {
    'titulo': 'Auxiliar cuenta',
    'hoja': 'auxiliar_cuenta',
    'columnas': _CUENTA + (('nombre', 'Nombre de cuenta', TEXTO),) + _SALDOS,
}
AUXILIAR_CONTACTO = {
    'titulo': 'Auxiliar por contacto',
    'hoja': 'auxiliar_contacto',
    'columnas': _CUENTA + _CONTACTO + _SALDOS,
}
AUXILIAR_GENERAL = {
    'titulo': 'Auxiliar general',
    'hoja': 'auxiliar_general',
    'columnas': _CUENTA + _CONTACTO + _ASIENTO + _SALDOS,
}
BASES = {
    'titulo': 'Informe de bases',
    'hoja': 'bases',
    'columnas': (
        ('codigo', 'Cuenta', TEXTO),
        ('nombre', 'Nombre Cuenta', TEXTO),
        ('identificacion', 'Identificación', TEXTO),
        ('contacto', 'Contacto', TEXTO),
        ('comprobante', 'Comprobante', TEXTO),
        ('numero', 'Numero', TEXTO),
        ('fecha', 'Fecha', FECHA),
        ('detalle', 'Detalle', TEXTO),
        ('debito', 'Debitos ($)', IMPORTE),
        ('credito', 'Creditos ($)', IMPORTE),
        ('base', 'Base ($)', IMPORTE),
    ),
}
CERTIFICADO_RETENCION = {
    'titulo': 'Certificado retenciones',
    # Único informe cuyo archivo no se llama como la hoja.
    'hoja': 'Certificado de retencion',
    'archivo': 'certificado_retencion',
    'columnas': (
        ('identificacion', 'Identificación', TEXTO),
        ('contacto', 'Contacto', TEXTO),
        ('codigo', 'Cuenta', TEXTO),
        ('nombre', 'Nombre cuenta', TEXTO),
        ('base_retenido', 'Monto del pago sujeto a retención ($)', IMPORTE),
        ('retenido', 'Retenido y consignado ($)', IMPORTE),
    ),
}
_ESTADO = (
    ('clase', 'Clase', TEXTO),
    ('grupo', 'Grupo', TEXTO),
    ('codigo', 'Codigo cuenta', TEXTO),
    ('nombre', 'Nombre cuenta', TEXTO),
    ('saldo', 'Saldo ($)', IMPORTE),
)
ESTADO_RESULTADOS = {
    'titulo': 'Estado de resultados',
    'hoja': 'estado_resultados',
    'columnas': _ESTADO,
}
ESTADO_SITUACION_FINANCIERA = {
    'titulo': 'Estado situacion financiera',
    'hoja': 'estado_situacion_financiera',
    'columnas': _ESTADO,
}


def excel(formato, filas, empresa, fecha_desde, fecha_hasta):
    """Devuelve los bytes del .xlsx de un informe, y el nombre del archivo."""
    columnas = formato['columnas']

    wb = Workbook()
    ws = wb.active
    ws.title = formato['hoja']

    anchos = [0] * len(columnas)
    _bloque_titulo(ws, formato['titulo'], empresa, fecha_desde, fecha_hasta, anchos)
    _encabezados(ws, columnas, anchos)

    for numero, fila in enumerate(filas, start=_FILA_ENCABEZADOS + 1):
        for indice, (campo, _, formato_numero) in enumerate(columnas):
            valor = fila[campo]
            celda = ws.cell(row=numero, column=indice + 1, value=valor)
            celda.font = Font(name=_FUENTE, size=10)
            celda.number_format = formato_numero
            anchos[indice] = max(anchos[indice], _largo(valor))

    for indice, ancho in enumerate(anchos):
        ws.column_dimensions[get_column_letter(indice + 1)].width = ancho + 1

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue(), f"{formato.get('archivo') or formato['hoja']}.xlsx"


PORCENTAJE = '0.00%'
_BORDE_TOTAL = Border(top=Side(style='thin'))
_FONDO_UTILIDAD = PatternFill('solid', fgColor='E6F6F9')


def excel_estado_resultados(filas, empresa, fecha_desde, fecha_hasta, desde_anterior, hasta_anterior):
    """
    El estado de resultados formal (`servicios.estado_resultados.filas`): el
    mismo bloque de título que los demás informes y, debajo, las secciones con
    el periodo, el mismo rango un año antes y la variación.
    """
    columnas = (
        ('codigo', 'Código', TEXTO),
        ('nombre', 'Concepto', TEXTO),
        ('actual', f'{fecha_desde} a {fecha_hasta} ($)', IMPORTE),
        ('anterior', f'{desde_anterior} a {hasta_anterior} ($)', IMPORTE),
        ('variacion', 'Variación ($)', IMPORTE),
        ('porcentaje', 'Variación (%)', PORCENTAJE),
    )

    wb = Workbook()
    ws = wb.active
    ws.title = 'estado_resultados'

    anchos = [0] * len(columnas)
    _bloque_titulo(ws, 'Estado de resultados', empresa, fecha_desde, fecha_hasta, anchos)
    _encabezados(ws, columnas, anchos)

    numero = _FILA_ENCABEZADOS
    for fila in filas:
        tipo = fila['tipo']
        # Una fila en blanco antes de cada sección y de cada utilidad, para que
        # el estado se lea por bloques.
        if tipo in (er.SECCION, er.UTILIDAD):
            numero += 1
        numero += 1
        for indice, (campo, _, formato_numero) in enumerate(columnas):
            valor = fila[campo]
            if campo == 'nombre' and tipo == er.CUENTA:
                valor = f'    {valor}'
            if campo == 'nombre' and tipo in (er.SECCION, er.UTILIDAD):
                valor = valor.upper()
            celda = ws.cell(row=numero, column=indice + 1, value=valor)
            celda.font = Font(name=_FUENTE, size=10, bold=tipo != er.CUENTA)
            celda.number_format = formato_numero
            if tipo == er.TOTAL and indice >= 2:
                celda.border = _BORDE_TOTAL
            if tipo == er.UTILIDAD:
                celda.fill = _FONDO_UTILIDAD
            anchos[indice] = max(anchos[indice], _largo(valor) if formato_numero != IMPORTE else _largo_importe(valor))

    for indice, ancho in enumerate(anchos):
        ws.column_dimensions[get_column_letter(indice + 1)].width = ancho + 1

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue(), 'estado_resultados_formal.xlsx'

# Negativos entre paréntesis: la convención de un estado financiero presentado.
IMPORTE_CONTABLE = '#,##0.00;(#,##0.00)'
_BORDE_DOBLE = Border(top=Side(style='thin'), bottom=Side(style='double'))
_FIRMAS = (
    ('Representante legal', 'C.C.'),
    ('Contador público', 'T.P.'),
    ('Revisor fiscal', 'T.P.'),
)


def excel_situacion_financiera(filas, empresa, fecha_corte, fecha_anterior):
    """
    El estado de situación financiera formal (`servicios.situacion_financiera`):
    el bloque de título con el corte, las secciones con el corte actual, el
    anterior y la variación, y al pie las líneas de firma.
    """
    columnas = [
        ('codigo', 'Código', TEXTO),
        ('nombre', 'Concepto', TEXTO),
        ('actual', f'{fecha_corte} ($)', IMPORTE_CONTABLE),
    ]
    if fecha_anterior is not None:
        columnas += [
            ('anterior', f'{fecha_anterior} ($)', IMPORTE_CONTABLE),
            ('variacion', 'Variación ($)', IMPORTE_CONTABLE),
            ('porcentaje', 'Variación (%)', PORCENTAJE),
        ]

    wb = Workbook()
    ws = wb.active
    ws.title = 'estado_situacion_financiera'

    anchos = [0] * len(columnas)
    rango = (f'Fecha de corte: {fecha_corte}',)
    if fecha_anterior is not None:
        rango += (f'Comparado con: {fecha_anterior}',)
    _bloque_titulo(ws, 'Estado de situación financiera', empresa, None, None, anchos, rango)
    _encabezados(ws, columnas, anchos)

    numero = _FILA_ENCABEZADOS
    for fila in filas:
        tipo = fila['tipo']
        # Una fila en blanco antes de cada sección y del total final, para que
        # el estado se lea por bloques.
        if tipo in (sf.SECCION, sf.TOTAL_FINAL):
            numero += 1
        numero += 1
        for indice, (campo, _, formato_numero) in enumerate(columnas):
            valor = fila[campo]
            if campo == 'nombre':
                if tipo in (sf.LINEA, sf.RESULTADO):
                    valor = f'        {valor}'
                elif tipo in (sf.SUBSECCION, sf.SUBTOTAL):
                    valor = f'    {valor}'
                elif tipo in (sf.SECCION, sf.TOTAL, sf.TOTAL_FINAL):
                    valor = valor.upper()
            celda = ws.cell(row=numero, column=indice + 1, value=valor)
            celda.font = Font(name=_FUENTE, size=10, bold=tipo not in (sf.LINEA, sf.RESULTADO))
            celda.number_format = formato_numero
            if indice >= 2:
                if tipo == sf.SUBTOTAL:
                    celda.border = _BORDE_TOTAL
                elif tipo in (sf.TOTAL, sf.TOTAL_FINAL):
                    celda.border = _BORDE_DOBLE
            if tipo == sf.TOTAL_FINAL:
                celda.fill = _FONDO_UTILIDAD
            anchos[indice] = max(
                anchos[indice],
                _largo_importe(valor) + 2 if formato_numero == IMPORTE_CONTABLE else _largo(valor),
            )

    # Las firmas van a mano: tres líneas con el cargo y el documento debajo.
    numero += 4
    for indice, (cargo, documento) in enumerate(_FIRMAS):
        columna = 2 + indice if len(columnas) > 3 else 1 + indice
        linea = ws.cell(row=numero, column=columna, value=cargo)
        linea.border = Border(top=Side(style='thin'))
        linea.font = Font(name=_FUENTE, size=10, bold=True)
        ws.cell(row=numero + 1, column=columna, value=documento).font = Font(name=_FUENTE, size=9)

    for indice, ancho in enumerate(anchos):
        ws.column_dimensions[get_column_letter(indice + 1)].width = max(ancho + 1, 18 if indice >= 2 else 0)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue(), f'estado_situacion_financiera_{fecha_corte}.xlsx'


def _largo_importe(valor):
    """Ancho de un importe como lo muestra el formato, con separador de miles."""
    return 0 if valor is None else len(f'{valor:,.2f}')


def _bloque_titulo(ws, titulo, empresa, fecha_desde, fecha_hasta, anchos, rango=None):
    # El fondo va solo en la celda de arriba a la izquierda: es la que Excel
    # pinta a lo ancho de la combinación.
    ultima = get_column_letter(len(anchos))
    encabezado = (
        (titulo, 14, True, 'center'),
        (empresa, 12, True, 'center'),
        (f'Fecha generación: {timezone.localtime():%Y-%m-%d %H:%M}', 8, False, 'right'),
    )
    for numero, (texto, tamano, negrita, alineacion) in enumerate(encabezado, start=1):
        ws.merge_cells(f'A{numero}:{ultima}{numero}')
        celda = ws.cell(row=numero, column=1, value=texto)
        celda.font = Font(name=_FUENTE, size=tamano, bold=negrita)
        celda.alignment = Alignment(horizontal=alineacion)
        celda.fill = _FONDO
        anchos[0] = max(anchos[0], _largo(texto))

    rango = rango or (f'Fecha desde: {fecha_desde}', f'Fecha hasta: {fecha_hasta}')
    for numero, texto in enumerate(rango, start=4):
        celda = ws.cell(row=numero, column=1, value=texto)
        celda.font = Font(name=_FUENTE, size=10)
        anchos[0] = max(anchos[0], _largo(texto))


def _encabezados(ws, columnas, anchos):
    for indice, (_, encabezado, _) in enumerate(columnas):
        celda = ws.cell(row=_FILA_ENCABEZADOS, column=indice + 1, value=encabezado)
        celda.font = Font(name=_FUENTE, size=10, bold=True)
        celda.fill = _FONDO
        anchos[indice] = max(anchos[indice], _largo(encabezado))


def _largo(valor):
    """Ancho que ocupa un valor, medido como lo escribe Python. Vacío no ocupa."""
    return 0 if valor is None else len(str(valor))
