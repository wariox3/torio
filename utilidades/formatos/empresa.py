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
import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from utilidades.formatos.pagina import ANCHO_CONTENIDO

GRIS_TITULO = colors.HexColor('#d9d9d9')
GRIS_PIE = colors.HexColor('#767676')

# Quién generó la hoja. Va arriba de todo, en letra mínima: sirve para saber de
# dónde salió un papel que alguien trae impreso, sin competir con el contenido.
ORIGEN = 'RedDoc | ERP'

# El recuadro del logotipo. El espacio se reserva siempre, haya imagen o no: si
# el bloque se corriera a la izquierda cuando falta el logo, dos impresiones del
# mismo formato saldrían con distinta caja.
LADO_LOGO = 2.4 * cm
SEPARACION_LOGO = 0.5 * cm

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
    logotipo a la izquierda y los datos del emisor a su derecha. El logotipo sale
    de `GenConfiguracion.gen_empresa_logotipo`; si el tenant no cargó ninguno,
    su espacio queda en blanco.

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
        self.configuracion = configuracion
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
            'origen': ParagraphStyle(
                'encabezado_origen', parent=base['Normal'],
                fontSize=5.5, alignment=TA_RIGHT, leading=7,
                textColor=GRIS_PIE,
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
        elementos = [self._origen()]
        if self.titulo:
            elementos.append(self._barra_titulo())
            elementos.append(Spacer(1, 0.55 * cm))
        elementos.append(self._logo_y_datos())
        return elementos

    def _origen(self):
        """
        Cuándo se imprimió y desde dónde, arriba a la derecha.

        La fecha va en hora local del servidor: es un dato para el que sostiene
        el papel —«¿esta copia es la última?»—, no para una máquina.
        """
        marca = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')
        return Paragraph(f'{marca} [{ORIGEN}]', self.estilos['origen'])

    def _barra_titulo(self):
        """
        La barra gris, alineada con los datos de la empresa y no con el margen.

        El espacio del logotipo queda libre a su izquierda: la barra arranca
        donde arranca la razón social, así que el bloque entero —título, nombre,
        NIT, dirección— forma una sola columna al lado del logo en vez de dos
        alineaciones distintas encimadas.
        """
        sangria = LADO_LOGO + SEPARACION_LOGO
        tabla = Table(
            [['', Paragraph(self.titulo, self.estilos['titulo'])]],
            colWidths=[sangria, self.ancho - sangria],
        )
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (1, 0), (1, 0), GRIS_TITULO),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 0),
        ]))
        return tabla

    def _logo_y_datos(self):
        """El logotipo y, al lado, los datos del emisor."""
        tabla = Table(
            [[self._logotipo(), self._datos()]],
            colWidths=[LADO_LOGO, self.ancho - LADO_LOGO],
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (1, 0), (1, 0), SEPARACION_LOGO),
        ]))
        return tabla

    def _logotipo(self):
        """
        El logotipo escalado dentro de su cuadro, o el cuadro vacío.

        Se escala a lo que entre sin deformarlo, y debajo se rellena hasta
        completar `LADO_LOGO` de alto: así la celda mide igual con logo ancho,
        con logo alto o sin logo, y el encabezado no cambia de tamaño entre un
        tenant y otro.

        Un logotipo ilegible se trata como si no estuviera. Que alguien haya
        guardado bytes rotos no es motivo para que no salga el documento.
        """
        datos = self._bytes_logotipo()
        if datos is None:
            return Spacer(LADO_LOGO, LADO_LOGO)

        try:
            ancho_px, alto_px = ImageReader(io.BytesIO(datos)).getSize()
            escala = min(LADO_LOGO / ancho_px, LADO_LOGO / alto_px)
            alto = alto_px * escala
            imagen = Image(io.BytesIO(datos), width=ancho_px * escala, height=alto)
        except Exception:
            return Spacer(LADO_LOGO, LADO_LOGO)

        imagen.hAlign = 'LEFT'
        if alto >= LADO_LOGO:
            return imagen
        return [imagen, Spacer(1, LADO_LOGO - alto)]

    def _bytes_logotipo(self):
        """
        Los bytes del logotipo, de la misma configuración que ya se leyó.

        El import va adentro por lo mismo que en `configuracion_actual`:
        `utilidades` no depende de una app en tiempo de carga.
        """
        from general.servicios import logotipo

        return logotipo.bytes_logotipo(self.configuracion)

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
