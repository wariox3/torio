"""
Formato de la factura de venta: la representación gráfica de la factura electrónica.

La factura electrónica es el XML firmado que valida la DIAN; esta hoja es lo que se
le entrega al cliente y lo que se archiva impreso. Por eso, además de lo comercial
—quién compra, qué, cuánto—, lleva lo que identifica la factura ante la DIAN: el
CUFE, el QR que lleva a consultarlo, la resolución de numeración con su rango y
vigencia, y con qué software se generó y quién lo fabrica.

Una factura todavía sin validar se imprime igual —sirve para revisarla antes de
emitir—, pero el bloque electrónico lo dice en vez de quedar en blanco: una hoja
sin CUFE que pareciera terminada podría entregarse como si fuera la factura.

A diferencia de los demás formatos, no usa `EncabezadoEmpresa`: la factura es lo
que ve el cliente, y lleva su propio encabezado de factura —la empresa a la
izquierda, el título y el número en un recuadro a la derecha—. Los datos sí salen
de la misma fuente, `datos_empresa`, para que el NIT y la dirección se armen igual
que en el resto del sistema. La caja de la hoja es la estándar
(`utilidades.formatos.pagina`).
"""
import io
from decimal import Decimal
from xml.sax.saxutils import escape

from django.db.models import Sum
from django.utils import timezone
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from general.formatos.base import FormatoBase
from general.models import GenDocumentoImpuesto
from utilidades.formatos import configuracion_actual, datos_empresa
from utilidades.formatos.pagina import ANCHO_CONTENIDO, anchos
from utilidades.numero_letras import valor_en_letras

CERO = Decimal('0')

_GRIS_ETIQUETA = colors.HexColor('#d9d9d9')
_GRIS_LINEA = colors.HexColor('#9e9e9e')
_GRIS_SUAVE = colors.HexColor('#f2f2f2')
_GRIS_TEXTO = colors.HexColor('#595959')
# El total a pagar es lo primero que se busca en una factura: va en negativo
# (texto claro sobre fondo oscuro) para que se encuentre sin leer la hoja.
_OSCURO = colors.HexColor('#3a3a3a')

# Con qué se generó la factura. Es software propio, así que en vez de un proveedor
# tecnológico la hoja dice cuál es el software, quién lo fabrica y en qué modalidad.
SOFTWARE = 'RedDoc ERP'
FABRICANTE_SOFTWARE = 'SEMÁNTICA DIGITAL S.A.S. — NIT 901192048-4'
MODALIDAD_SOFTWARE = 'Software propio'

# La consulta pública de la DIAN. Es lo que codifica el QR cuando rededoc no
# devolvió el suyo: con el CUFE basta para que cualquiera verifique la factura.
URL_CONSULTA_DIAN = 'https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={cufe}'

# Adquiriente a la izquierda, datos de la factura a la derecha.
_ANCHO_PARTES = anchos(0.56, 0.02, 0.42)
_ANCHO_ETIQUETA_PARTE = 3.2 * cm

# Código, descripción, cantidad, precio, descuento, impuesto y total. La
# descripción se lleva lo que sobra: es lo que se parte en renglones.
_ANCHO_DETALLES = anchos(0.11, 0.35, 0.08, 0.12, 0.10, 0.11, 0.13)

# El resumen: letras, comentarios y pago a la izquierda; totales a la derecha,
# bajo las tres últimas columnas de la tabla de detalles.
_ANCHO_TOTALES = sum(_ANCHO_DETALLES[-3:])
_ANCHO_RESUMEN = [ANCHO_CONTENIDO - _ANCHO_TOTALES, _ANCHO_TOTALES]

LADO_QR = 3.2 * cm

# El encabezado: logotipo, datos de la empresa y el recuadro del título. El
# espacio del logotipo se reserva siempre, haya imagen o no, para que la empresa
# arranque en el mismo lugar en todos los tenants.
LADO_LOGO = 2.6 * cm
_ANCHO_TITULO = 6.4 * cm
_ANCHO_ENCABEZADO = [LADO_LOGO, ANCHO_CONTENIDO - LADO_LOGO - _ANCHO_TITULO, _ANCHO_TITULO]


class FormatoDocumentoFactura(FormatoBase):
    """
    Factura de venta: partes, detalles, totales y bloque electrónico.

    Numera sus páginas: una factura larga que se reparte en varias hojas tiene que
    poder armarse de nuevo, y el cliente saber que no le falta ninguna.

    Todas las filas de datos se imprimen aunque falte el valor, por lo mismo que el
    encabezado de empresa: la hoja mide igual en todas las facturas, y un dato que
    falta queda a la vista en vez de desaparecer.
    """

    numerar_paginas = True

    # El título de la tarjeta con los datos del documento, a la derecha del
    # adquiriente. Los formatos que heredan de la factura cambian solo esto.
    titulo_datos = 'DATOS DE LA FACTURA'

    def construir(self):
        documento = self.documento
        estilos = self._estilos()
        configuracion = configuracion_actual()

        return [
            self._encabezado(documento, configuracion, estilos),
            Spacer(1, 0.3 * cm),
            self._partes(documento, estilos),
            Spacer(1, 0.5 * cm),
            self._detalles(documento, estilos),
            Spacer(1, 0.4 * cm),
            self._resumen(documento, configuracion, estilos),
            Spacer(1, 0.5 * cm),
            self._electronico(documento, configuracion, estilos),
        ]

    # ------------------------------------------------------------- estilos ----

    @staticmethod
    def _estilos():
        base = getSampleStyleSheet()['Normal']

        def estilo(nombre, **kwargs):
            return ParagraphStyle(f'factura_{nombre}', parent=base, **kwargs)

        return {
            'razon_social': estilo('razon_social', fontName='Helvetica-Bold', fontSize=10, leading=13),
            'empresa': estilo('empresa', fontSize=8, leading=10.5),
            'titulo': estilo(
                'titulo', fontName='Helvetica-Bold', fontSize=13, leading=16, alignment=TA_CENTER,
            ),
            'numero_titulo': estilo(
                'numero_titulo', fontName='Helvetica-Bold', fontSize=14, leading=17, alignment=TA_CENTER,
            ),
            'seccion': estilo('seccion', fontName='Helvetica-Bold', fontSize=8, leading=10),
            'etiqueta': estilo('etiqueta', fontName='Helvetica-Bold', fontSize=7.5, leading=9),
            'valor': estilo('valor', fontSize=7.5, leading=9),
            'columna': estilo(
                'columna', fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=TA_CENTER,
            ),
            'celda': estilo('celda', fontSize=7.5, leading=9.5),
            'cifra': estilo('cifra', fontSize=7.5, leading=9.5, alignment=TA_RIGHT),
            'conteo': estilo('conteo', fontSize=7, leading=9, textColor=_GRIS_TEXTO),
            'total_etiqueta': estilo('total_etiqueta', fontSize=8, leading=11),
            'total_valor': estilo('total_valor', fontSize=8, leading=11, alignment=TA_RIGHT),
            'pagar_etiqueta': estilo(
                'pagar_etiqueta', fontName='Helvetica-Bold', fontSize=9, leading=12,
                textColor=colors.white,
            ),
            'pagar_valor': estilo(
                'pagar_valor', fontName='Helvetica-Bold', fontSize=9, leading=12,
                alignment=TA_RIGHT, textColor=colors.white,
            ),
            'texto': estilo('texto', fontSize=7.5, leading=10),
            'informacion': estilo('informacion', fontSize=7, leading=9, textColor=_GRIS_TEXTO),
            'informacion_pago': estilo('informacion_pago', fontSize=7.5, leading=10),
            'cufe': estilo('cufe', fontName='Courier', fontSize=6, leading=7.5),
            'aviso': estilo(
                'aviso', fontName='Helvetica-Bold', fontSize=6.5, leading=8.5, textColor=_GRIS_TEXTO,
            ),
            'electronico_titulo': estilo(
                'electronico_titulo', fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=_OSCURO,
            ),
            'electronico_etiqueta': estilo(
                'electronico_etiqueta', fontName='Helvetica-Bold', fontSize=5.5, leading=7.5,
                textColor=_GRIS_TEXTO,
            ),
            'electronico_valor': estilo('electronico_valor', fontSize=6.5, leading=8),
        }

    # ------------------------------------------------------------ utilidades ----

    @staticmethod
    def _texto(valor):
        """
        El valor listo para un `Paragraph`, que interpreta marcado: una razón social
        con «&» o una descripción con «<» romperían la hoja si no se escaparan.
        """
        return '' if valor is None else escape(str(valor))

    @staticmethod
    def _moneda(valor):
        return f'{valor or CERO:,.2f}'

    @staticmethod
    def _cantidad(valor):
        return f'{valor or CERO:,.2f}'

    @staticmethod
    def _numero(documento):
        """
        «FE2813»: el prefijo de la resolución pegado al número, como lo numera la DIAN.
        Sin número, el recuadro queda en blanco pero con su alto.
        """
        if documento.numero is None:
            return '&nbsp;'
        prefijo = documento.resolucion.prefijo if documento.resolucion_id else ''
        return escape(f'{prefijo or ""}{documento.numero}')

    def _filas(self, pares, estilos):
        return [
            [Paragraph(f'{etiqueta}:', estilos['etiqueta']), Paragraph(valor, estilos['valor'])]
            for etiqueta, valor in pares
        ]

    # ------------------------------------------------------------ encabezado ----

    def _encabezado(self, documento, configuracion, estilos):
        """
        La empresa a la izquierda y, a la derecha, qué documento es: el título y, debajo,
        el número en un recuadro fino. Los dos arrancan a la misma altura, arriba.
        """
        tabla = Table(
            [[self._logotipo(configuracion), self._empresa(configuracion, estilos),
              self._recuadro_titulo(documento, estilos)]],
            colWidths=_ANCHO_ENCABEZADO,
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('LEFTPADDING', (1, 0), (1, 0), 12),
            ('RIGHTPADDING', (-1, 0), (-1, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return tabla

    def _informacion_superior(self, configuracion, estilos):
        """
        El texto libre que la empresa quiere arriba de la factura
        (`ven_factura_informacion_superior`): va debajo de sus datos, en el mismo
        bloque y alineado con ellos, con sus saltos de línea. Sin texto no sale nada,
        ni siquiera el renglón: no es un dato de la factura que tenga que quedar a la
        vista cuando falta.
        """
        texto = (getattr(configuracion, 'ven_factura_informacion_superior', None) or '').strip()
        if not texto:
            return []
        return [
            Spacer(1, 4),
            Paragraph('<br/>'.join(self._texto(linea) for linea in texto.splitlines()),
                      estilos['informacion']),
        ]

    def _empresa(self, configuracion, estilos):
        """
        La razón social en negrita y, debajo, en mayúsculas: el NIT con el tipo de
        persona, la dirección con la ciudad y el teléfono.

        Las líneas salen aunque el dato falte, igual que en el encabezado estándar:
        el bloque mide lo mismo en todos los tenants y lo que falta queda a la vista.
        La ciudad va sola, sin el departamento que trae `datos_empresa`.
        """
        empresa = datos_empresa(configuracion)
        tipo_persona = getattr(configuracion, 'gen_empresa_tipo_persona', None)
        ciudad = getattr(configuracion, 'gen_empresa_ciudad', None)

        def unidos(*partes):
            return ' - '.join(parte for parte in partes if parte)

        lineas = (
            ('NIT', unidos(empresa['nit'], tipo_persona and f'PERSONA {tipo_persona.nombre}')),
            ('DIRECCIÓN', unidos(empresa['direccion'], ciudad and ciudad.nombre)),
            ('TEL', empresa['telefono']),
        )
        elementos = [Paragraph(self._texto(empresa['razon_social'].upper()) or '&nbsp;',
                               estilos['razon_social'])]
        for etiqueta, valor in lineas:
            elementos.append(Paragraph(
                f'{etiqueta}: {self._texto(valor.upper())}', estilos['empresa'],
            ))
        elementos.extend(self._informacion_superior(configuracion, estilos))
        return elementos

    def _recuadro_titulo(self, documento, estilos):
        """
        El título suelto, sin franja, y el número en un recuadro de línea fina y
        esquinas redondeadas. La fecha de emisión no va acá: ya está en los datos de
        la factura.
        """
        numero = Table(
            [[Paragraph(self._numero(documento), estilos['numero_titulo'])]],
            colWidths=[_ANCHO_TITULO],
            cornerRadii=[3, 3, 3, 3],
        )
        numero.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.8, _GRIS_ETIQUETA),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        return [
            Paragraph(self._texto(documento.documento_tipo.nombre.upper()), estilos['titulo']),
            Spacer(1, 10),
            numero,
        ]

    @staticmethod
    def _logotipo(configuracion):
        """
        El logotipo escalado a su cuadro sin deformarlo, o el cuadro vacío.

        Un logotipo ilegible se trata como si no estuviera: que alguien haya guardado
        bytes rotos no es motivo para que no salga la factura.
        """
        # El import va acá y no arriba: `general.servicios` carga
        # `documento_imprimir`, que importa los formatos, y desde el módulo sería
        # circular si algo importa `general.formatos` antes que los servicios.
        from general.servicios import logotipo

        datos = logotipo.bytes_logotipo(configuracion)
        if datos is None:
            return Spacer(LADO_LOGO, LADO_LOGO)
        try:
            ancho_px, alto_px = ImageReader(io.BytesIO(datos)).getSize()
            escala = min(LADO_LOGO / ancho_px, LADO_LOGO / alto_px)
            imagen = Image(io.BytesIO(datos), width=ancho_px * escala, height=alto_px * escala)
        except Exception:
            return Spacer(LADO_LOGO, LADO_LOGO)
        imagen.hAlign = 'LEFT'
        return imagen

    # ---------------------------------------------------------------- partes ----

    def _partes(self, documento, estilos):
        """Quién compra, a la izquierda; qué factura es y cómo se paga, a la derecha."""
        tabla = Table(
            [[self._adquiriente(documento, estilos), '', self._datos_factura(documento, estilos)]],
            colWidths=_ANCHO_PARTES,
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return tabla

    def _adquiriente(self, documento, estilos):
        contacto = documento.contacto
        identificacion = ''
        ciudad = ''
        correo = ''
        if contacto is not None:
            tipo = contacto.identificacion.abreviatura if contacto.identificacion_id else ''
            numero = contacto.numero_identificacion or ''
            if contacto.digito_verificacion:
                numero = f'{numero}-{contacto.digito_verificacion}'
            identificacion = f'{tipo} {numero}'.strip()
            ciudad = contacto.ciudad.nombre if contacto.ciudad_id else ''
            # El de facturación electrónica es a donde el cliente quiere recibir
            # las facturas; el general, si no dio otro.
            correo = contacto.correo_facturacion_electronica or contacto.correo

        pares = (
            ('CLIENTE', self._texto(contacto and contacto.nombre_corto)),
            ('IDENTIFICACIÓN', self._texto(identificacion)),
            ('DIRECCIÓN', self._texto(contacto and contacto.direccion)),
            ('CIUDAD', self._texto(ciudad)),
            ('TELÉFONO', self._texto(contacto and contacto.telefono)),
            ('CORREO', self._texto(correo)),
        )
        return self._tarjeta('ADQUIRIENTE', self._filas(pares, estilos), estilos,
                             _ANCHO_PARTES[0])

    def _datos_factura(self, documento, estilos):
        plazo = documento.plazo_pago
        credito = bool(plazo and plazo.dias > 0)
        pares = (
            ('FECHA EMISIÓN', self._texto(documento.fecha)),
            ('VENCIMIENTO', self._texto(documento.fecha_vence)),
            ('FORMA DE PAGO', 'Crédito' if credito else 'Contado'),
            ('MEDIO DE PAGO', self._texto(documento.metodo_pago and documento.metodo_pago.nombre)),
            ('PLAZO', self._texto(plazo and plazo.nombre)),
            ('ORDEN DE COMPRA', self._texto(documento.orden_compra)),
        )
        # El número no va acá: está en el recuadro del encabezado, que es donde se
        # busca primero.
        return self._tarjeta(self.titulo_datos, self._filas(pares, estilos), estilos,
                             _ANCHO_PARTES[2])

    def _tarjeta(self, titulo, filas, estilos, ancho):
        """Un recuadro con su título en una franja gris y las filas de etiqueta y valor."""
        datos = [[Paragraph(titulo, estilos['seccion']), '']] + filas
        tabla = Table(datos, colWidths=[_ANCHO_ETIQUETA_PARTE, ancho - _ANCHO_ETIQUETA_PARTE])
        tabla.setStyle(TableStyle([
            ('SPAN', (0, 0), (-1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), _GRIS_ETIQUETA),
            ('BOX', (0, 0), (-1, -1), 0.5, _GRIS_LINEA),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            # La primera fila de datos con un poco de aire bajo la franja del título.
            ('TOPPADDING', (0, 1), (-1, 1), 3),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        return tabla

    # -------------------------------------------------------------- detalles ----

    def _detalles(self, documento, estilos):
        encabezados = ('CÓDIGO', 'DESCRIPCIÓN', 'CANT.', 'PRECIO', 'DESC.', 'IMPUESTO', 'TOTAL')
        filas = [[Paragraph(texto, estilos['columna']) for texto in encabezados]]

        # Solo las líneas de ítem: una factura no lleva apuntes contables.
        lineas = [
            detalle for detalle in documento.documentos_detalles_documento_rel.all()
            if detalle.item_id
        ]
        for detalle in lineas:
            filas.append([
                Paragraph(self._texto(detalle.item.codigo), estilos['celda']),
                Paragraph(self._texto(detalle.detalle or detalle.item.nombre), estilos['celda']),
                Paragraph(self._cantidad(detalle.cantidad), estilos['cifra']),
                Paragraph(self._moneda(detalle.precio), estilos['cifra']),
                Paragraph(self._moneda(detalle.descuento), estilos['cifra']),
                Paragraph(self._moneda(detalle.impuesto), estilos['cifra']),
                Paragraph(self._moneda(detalle.total), estilos['cifra']),
            ])
        ultima_linea = len(filas) - 1
        filas.append([
            Paragraph(f'Cantidad de ítems: {len(lineas)}', estilos['conteo']),
            '', '', '', '', '', '',
        ])

        estilo = [
            ('BACKGROUND', (0, 0), (-1, 0), _GRIS_ETIQUETA),
            ('LINEBELOW', (0, 0), (-1, 0), 0.6, _GRIS_LINEA),
            ('BOX', (0, 0), (-1, ultima_linea), 0.5, _GRIS_LINEA),
            ('SPAN', (0, -1), (-1, -1)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
        # Una franja sí y otra no: en una factura larga el ojo no se salta de
        # renglón al seguir una línea hasta su total.
        for fila in range(2, ultima_linea + 1, 2):
            estilo.append(('BACKGROUND', (0, fila), (-1, fila), _GRIS_SUAVE))

        tabla = Table(filas, colWidths=_ANCHO_DETALLES, repeatRows=1)
        tabla.setStyle(TableStyle(estilo))
        return tabla

    # --------------------------------------------------------------- resumen ----

    def _resumen(self, documento, configuracion, estilos):
        """El valor en letras, los comentarios y el pago al lado de los totales."""
        tabla = Table(
            [[self._notas(documento, configuracion, estilos), self._totales(documento, estilos)]],
            colWidths=_ANCHO_RESUMEN,
        )
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (0, 0), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return tabla

    def _notas(self, documento, configuracion, estilos):
        """
        Valor en letras, comentarios e información de pago. Bajo el título de la
        información de pago va el texto libre de la empresa
        (`ven_factura_informacion_inferior`), con sus saltos de línea; la cuenta del
        documento, si tiene, sigue en la línea del título.
        """
        banco = documento.cuenta_banco
        pago = ''
        if banco is not None:
            tipo = banco.cuenta_banco_tipo.nombre if banco.cuenta_banco_tipo_id else ''
            pago = ' '.join(parte for parte in (tipo, banco.nombre, banco.numero_cuenta) if parte)

        notas = [
            Paragraph(f'<b>VALOR EN LETRAS:</b> {valor_en_letras(documento.total)}', estilos['texto']),
            Spacer(1, 0.25 * cm),
            Paragraph(f'<b>COMENTARIOS:</b> {self._texto(documento.comentario)}', estilos['texto']),
            Spacer(1, 0.25 * cm),
            Paragraph(f'<b>INFORMACIÓN DE PAGO:</b> {self._texto(pago)}', estilos['texto']),
        ]
        inferior = (getattr(configuracion, 'ven_factura_informacion_inferior', None) or '').strip()
        if inferior:
            notas += [
                Spacer(1, 2),
                Paragraph('<br/>'.join(self._texto(linea) for linea in inferior.splitlines()),
                          estilos['informacion_pago']),
            ]
        return notas

    @staticmethod
    def _impuestos_por_nombre(documento):
        """
        Un renglón por impuesto con su nombre y lo que suma en la factura: primero
        los que se cobran (IVA, ICA…) y después las retenciones, que son los de
        operación negativa. Una factura con IVA y retención muestra los dos.
        """
        return [
            (fila['impuesto__nombre'], fila['valor'])
            for fila in GenDocumentoImpuesto.objects
            .filter(documento_detalle__documento=documento)
            .values('impuesto_id', 'impuesto__nombre', 'impuesto__operacion')
            .annotate(valor=Sum('total'))
            .order_by('-impuesto__operacion', 'impuesto_id')
        ]

    def _totales(self, documento, estilos):
        lineas = (
            ('Subtotal', documento.subtotal),
            ('Descuento', documento.descuento),
            *self._impuestos_por_nombre(documento),
        )
        filas = [
            [Paragraph(etiqueta, estilos['total_etiqueta']),
             Paragraph(self._moneda(valor), estilos['total_valor'])]
            for etiqueta, valor in lineas
        ]
        filas.append([
            Paragraph('TOTAL A PAGAR', estilos['pagar_etiqueta']),
            Paragraph(self._moneda(documento.total), estilos['pagar_valor']),
        ])

        tabla = Table(filas, colWidths=[_ANCHO_TOTALES * 0.5, _ANCHO_TOTALES * 0.5])
        tabla.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, _GRIS_LINEA),
            ('LINEBELOW', (0, 0), (-1, -3), 0.25, _GRIS_ETIQUETA),
            ('BACKGROUND', (0, -1), (-1, -1), _OSCURO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, -1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 5),
        ]))
        return tabla

    # ----------------------------------------------------------- electrónico ----

    def _electronico(self, documento, configuracion, estilos):
        """
        El QR a la izquierda y, a la derecha, lo que identifica la factura ante la DIAN.

        Sin CUFE la factura no está validada: en vez del QR y el CUFE sale el aviso.
        La resolución y el proveedor se imprimen igual, porque no dependen de la
        validación.
        """
        cufe = documento.cue
        resolucion = documento.resolucion

        if resolucion is not None:
            texto_resolucion = (
                f'N° {self._texto(resolucion.numero)} del {self._texto(resolucion.fecha_desde)}, '
                f'prefijo {self._texto(resolucion.prefijo) or "sin prefijo"}, rango del '
                f'{resolucion.consecutivo_desde} al {resolucion.consecutivo_hasta}, '
                f'vigente hasta el {self._texto(resolucion.fecha_hasta)}'
            )
        else:
            texto_resolucion = ''

        validacion = ''
        if documento.fecha_validacion:
            validacion = timezone.localtime(documento.fecha_validacion).strftime('%Y-%m-%d %H:%M:%S')

        if cufe:
            primera = ('CUFE', Paragraph(escape(cufe), estilos['cufe']))
        else:
            primera = ('ESTADO', Paragraph(
                'DOCUMENTO SIN VALIDAR ANTE LA DIAN: todavía no tiene CUFE.', estilos['aviso'],
            ))
        pares = (
            primera,
            ('RESOLUCIÓN DIAN', texto_resolucion),
            ('FECHA VALIDACIÓN', validacion),
            ('SOFTWARE', f'{SOFTWARE} · {MODALIDAD_SOFTWARE}'),
            ('FABRICANTE', FABRICANTE_SOFTWARE),
        )
        ancho_detalle = ANCHO_CONTENIDO - LADO_QR - 0.4 * cm
        filas = [[Paragraph('REPRESENTACIÓN GRÁFICA DE LA FACTURA ELECTRÓNICA DE VENTA',
                            estilos['electronico_titulo']), '']]
        for etiqueta, valor in pares:
            if isinstance(valor, str):
                valor = Paragraph(valor, estilos['electronico_valor'])
            filas.append([Paragraph(etiqueta, estilos['electronico_etiqueta']), valor])

        detalle = Table(filas, colWidths=[2.6 * cm, ancho_detalle - 2.6 * cm - 12])
        detalle.setStyle(TableStyle([
            ('SPAN', (0, 0), (-1, 0)),
            ('LINEBELOW', (0, 0), (-1, 0), 0.4, _GRIS_ETIQUETA),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 3),
            ('TOPPADDING', (0, 1), (-1, 1), 4),
        ]))

        tabla = Table(
            [[self._qr(documento, configuracion), detalle]],
            colWidths=[LADO_QR + 0.4 * cm, ancho_detalle],
        )
        # Sin recuadro: el QR arranca en el margen, como el resto de la hoja, y una
        # línea fina lo separa de los datos.
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (1, 0), (1, 0), 12),
            ('LINEBEFORE', (1, 0), (1, 0), 0.4, _GRIS_ETIQUETA),
        ]))
        return tabla

    @classmethod
    def _qr(cls, documento, configuracion):
        """
        El QR que lleva a la consulta de la factura en la DIAN.

        Manda el que devolvió rededoc (`documento.qr`); si no hay, se arma con el
        CUFE. Sin ninguno de los dos la factura no está validada, y el QR lleva sus
        datos (`_contenido_qr_sin_validar`) para que el espacio no quede en blanco.
        """
        contenido = documento.qr or (
            URL_CONSULTA_DIAN.format(cufe=documento.cue) if documento.cue else ''
        ) or cls._contenido_qr_sin_validar(documento, configuracion)

        widget = QrCodeWidget(contenido)
        x1, y1, x2, y2 = widget.getBounds()
        dibujo = Drawing(
            LADO_QR, LADO_QR,
            transform=[LADO_QR / (x2 - x1), 0, 0, LADO_QR / (y2 - y1), 0, 0],
        )
        dibujo.add(widget)
        return dibujo

    @staticmethod
    def _contenido_qr_sin_validar(documento, configuracion):
        """
        Los datos de una factura que la DIAN todavía no validó, con las mismas claves
        del QR de la DIAN (`NumFac`, `FecFac`, `NitFac`…).

        No lleva CUFE ni la URL de consulta, y la primera línea dice que no está
        validada: quien lo escanee ve qué factura es, pero no llega a nada que la
        haga pasar por válida.
        """
        prefijo = (documento.resolucion.prefijo or '') if documento.resolucion_id else ''
        numero = f'{prefijo}{documento.numero}' if documento.numero is not None else ''
        contacto = documento.contacto
        pares = (
            ('NumFac', numero),
            ('FecFac', documento.fecha or ''),
            ('NitFac', datos_empresa(configuracion)['nit']),
            ('DocAdq', contacto.numero_identificacion if contacto is not None else ''),
            ('ValFac', f'{documento.subtotal or CERO:.2f}'),
            ('ValIva', f'{documento.impuesto or CERO:.2f}'),
            ('ValTolFac', f'{documento.total or CERO:.2f}'),
        )
        return '\n'.join(
            ['FACTURA SIN VALIDAR ANTE LA DIAN', *(f'{clave}: {valor}' for clave, valor in pares)]
        )
