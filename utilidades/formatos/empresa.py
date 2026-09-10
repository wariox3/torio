"""
Los datos de la empresa y su encabezado, para todos los formatos impresos.

Antes de esto cada salida armaba el bloque por su cuenta: el Excel de informes
solo ponía la razón social, el certificado de retención le sumaba NIT, dirección
y teléfono, y la factura electrónica repetía las mismas propiedades para el XML.
Tres lecturas de `GenConfiguracion` con tres criterios distintos sobre lo mismo,
que iban a divergir apenas se sumara un formato más.

Acá hay dos piezas y conviene no mezclarlas:

- `datos_empresa` normaliza la configuración —el NIT con su dígito, la ciudad con
  su departamento, los vacíos como cadena vacía y no como `None`—. Es lo que
  cualquier salida necesita, sea PDF, Excel o XML.
- `EncabezadoEmpresa` dibuja el bloque en reportlab. Solo sirve para PDF.

El encabezado sale **siempre**, con datos o sin ellos. Es la parte estándar de
todos los formatos, y su alto tiene que ser el mismo en todos: si las líneas sin
dato desaparecieran, dos impresiones del mismo formato en dos tenants quedarían
con el cuerpo a distinta altura. Así que las etiquetas se imprimen igual y lo que
falta queda en blanco, a la vista de quien tenga que ir a completarlo.
"""
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from utilidades.formatos.pagina import ANCHO_CONTENIDO

GRIS_TITULO = colors.HexColor('#d9d9d9')
GRIS_MARCO = colors.HexColor('#bdbdbd')

# El recuadro del logo. Todavía no está definido de dónde sale la imagen, así que
# por ahora se reserva el espacio: el día que se resuelva, el logo entra acá sin
# recorrer los formatos moviendo el resto del encabezado.
LADO_LOGO = 2.4 * cm
_SEPARACION_LOGO = 0.5 * cm

# Las líneas del bloque, en orden. La etiqueta va delante del valor; la razón
# social no lleva porque es el nombre, no un dato más.
_LINEAS = (
    ('NIT', 'nit'),
    ('DIRECCIÓN', 'direccion'),
    ('TEL', 'telefono'),
    ('CORREO', 'correo'),
)

_CLAVES = ('razon_social', 'nombre_corto', 'nit', 'direccion',
           'telefono', 'correo', 'ciudad')


def _texto(valor):
    """Un vacío es cadena vacía y no `None`: el que imprime no debería tener que mirarlo."""
    return '' if valor is None else str(valor).strip()


def configuracion_actual():
    """
    La `GenConfiguracion` del tenant, o `None` si todavía no existe.

    El id 1 lo siembra el fixture de cada tenant, así que en la práctica está;
    pero un formato no debería reventar por un tenant a medio crear, y el import
    va adentro para que `utilidades` no dependa de una app en tiempo de carga.
    """
    from general.models import GenConfiguracion

    return (
        GenConfiguracion.objects
        .select_related('gen_empresa_ciudad__estado')
        .first()
    )


def datos_empresa(configuracion):
    """
    Los datos del emisor, normalizados, desde `GenConfiguracion`.

    Devuelve siempre las mismas claves, con cadena vacía donde el tenant no
    cargó el dato, para que quien imprima decida qué mostrar sin repetir la
    lógica de armado.
    """
    if configuracion is None:
        return {clave: '' for clave in _CLAVES}

    return {
        'razon_social': _texto(configuracion.gen_empresa_razon_social),
        'nombre_corto': _texto(configuracion.gen_empresa_nombre_corto),
        'nit': _nit(configuracion),
        'direccion': _texto(configuracion.gen_empresa_direccion),
        'telefono': _texto(configuracion.gen_empresa_telefono),
        'correo': _texto(configuracion.gen_empresa_correo),
        'ciudad': _ciudad(configuracion),
    }


def _nit(configuracion):
    """El número con su dígito de verificación: así se identifica a la empresa."""
    numero = _texto(configuracion.gen_empresa_numero_identificacion)
    digito = _texto(configuracion.gen_empresa_digito_verificacion)
    if numero and digito:
        return f'{numero}-{digito}'
    return numero


def _ciudad(configuracion):
    """«MEDELLÍN - ANTIOQUIA»; solo la ciudad si no se trajo el departamento."""
    ciudad = configuracion.gen_empresa_ciudad
    if ciudad is None:
        return ''
    estado = ciudad.estado
    if estado is None:
        return ciudad.nombre.upper()
    return f'{ciudad.nombre.upper()} - {estado.nombre.upper()}'


class EncabezadoEmpresa:
    """
    El bloque de encabezado de un formato impreso.

    Tres partes, en este orden: la barra gris con el título del formato, el
    recuadro del logo a la izquierda y los datos del emisor a su derecha.

    Sale completo aunque el tenant no haya cargado nada: las etiquetas se
    imprimen igual con el valor en blanco, para que el alto del bloque no dependa
    de qué tan llena esté la configuración.

    Si no se pasa `configuracion`, la busca; si no se pasa `ancho`, ocupa el de la
    hoja estándar. Un formato que solo quiere el encabezado no tiene que calcular
    ni leer nada.
    """

    def __init__(self, configuracion=..., titulo=None, ancho=None, estilos=None):
        if configuracion is ...:
            configuracion = configuracion_actual()
        # El ancho no lo decide cada formato: la barra del título tiene que
        # cruzar la hoja, y con `None` reportlab la encogería al texto.
        ancho = ANCHO_CONTENIDO if ancho is None else ancho
        self.datos = datos_empresa(configuracion)
        self.titulo = titulo
        self.ancho = ancho
        self.estilos = estilos or self.estilos_por_defecto()

    @staticmethod
    def estilos_por_defecto():
        base = getSampleStyleSheet()
        return {
            'titulo': ParagraphStyle(
                'encabezado_titulo', parent=base['Normal'],
                fontName='Helvetica-Bold', fontSize=10,
                alignment=TA_CENTER, leading=13,
            ),
            'razon_social': ParagraphStyle(
                'encabezado_razon_social', parent=base['Normal'],
                fontName='Helvetica-Bold', fontSize=10, leading=13,
            ),
            'dato': ParagraphStyle(
                'encabezado_dato', parent=base['Normal'],
                fontSize=8, leading=11,
            ),
        }

    def construir(self):
        """Los flowables del bloque."""
        elementos = []
        if self.titulo:
            elementos.append(self._barra_titulo())
            elementos.append(Spacer(1, 0.55 * cm))
        elementos.append(self._logo_y_datos())
        return elementos

    def _barra_titulo(self):
        tabla = Table(
            [[Paragraph(self.titulo, self.estilos['titulo'])]],
            colWidths=[self.ancho],
        )
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), GRIS_TITULO),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return tabla

    def _logo_y_datos(self):
        """El recuadro del logo y, al lado, los datos del emisor."""
        tabla = Table(
            [[Spacer(LADO_LOGO, LADO_LOGO), self._datos()]],
            colWidths=[LADO_LOGO, self.ancho - LADO_LOGO],
        )
        tabla.setStyle(TableStyle([
            # El marco marca el espacio reservado del logo mientras no haya imagen.
            ('BOX', (0, 0), (0, 0), 0.6, GRIS_MARCO),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (1, 0), (1, 0), _SEPARACION_LOGO),
        ]))
        return tabla

    def _datos(self):
        """
        Razón social y las líneas etiquetadas, siempre las mismas.

        Un valor que falta deja su etiqueta con el espacio en blanco en vez de
        quitar la línea, para que el bloque mida igual en todos los tenants.
        """
        elementos = [
            Paragraph(
                self.datos['razon_social'].upper() or '&nbsp;',
                self.estilos['razon_social'],
            )
        ]
        for etiqueta, clave in _LINEAS:
            elementos.append(
                Paragraph(f'{etiqueta}: {self.datos[clave]}', self.estilos['dato'])
            )
        return elementos
