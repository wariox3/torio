"""
Formato del tiquete del punto de venta (POS): la factura que sale por la impresora
térmica, en rollo de 80 mm.

Es una columna angosta que se lee de arriba a abajo —empresa, cliente, ítems,
totales e impuestos—, separada por renglones de guiones como los tiquetes de caja.
No hay espacio para la tarjeta del adquiriente ni para la tabla de siete columnas
de la factura en hoja: cada ítem es su descripción, la cantidad y el subtotal.

El POS electrónico (`FormatoDocumentoPosElectronico`) es el mismo tiquete con lo
que lo identifica ante la DIAN al final: la resolución, el CUFE, la fecha de
validación y el QR. El contenido del QR sale de la factura electrónica, para que
los dos documentos lleven a la misma consulta.

Los montos van sin decimales: en caja se cobra en pesos enteros, y en 72 mm las
dos cifras de más le quitan espacio a la descripción.
"""
from decimal import Decimal
from xml.sax.saxutils import escape

from django.db.models import Sum
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle

from general.formatos.base import FormatoBase
from general.formatos.documento_factura import (
    FABRICANTE_SOFTWARE,
    MODALIDAD_SOFTWARE,
    SOFTWARE,
    FormatoDocumentoFactura,
    dibujo_qr,
)
from general.models import GenDocumentoImpuesto
from utilidades.formatos import configuracion_actual, datos_empresa
from utilidades.formatos.pagina import ANCHO_CONTENIDO_ROLLO as ANCHO

CERO = Decimal('0')

_GRIS_GUION = colors.HexColor('#595959')

# Ítem, cantidad y subtotal. La descripción se lleva lo que sobra: es lo que se
# parte en renglones.
_ANCHO_DETALLES = [ANCHO * 0.56, ANCHO * 0.16, ANCHO * 0.28]
# Descripción del impuesto, base y valor.
_ANCHO_IMPUESTOS = [ANCHO * 0.44, ANCHO * 0.28, ANCHO * 0.28]
# Etiqueta y valor de los totales.
_ANCHO_TOTALES = [ANCHO * 0.65, ANCHO * 0.35]

LADO_QR = 3.5 * cm
# El CUFE son 96 caracteres sin espacios: `Paragraph` no parte una palabra, así
# que se corta a mano en renglones que caben en el rollo con su letra.
_CARACTERES_CUFE = 48


class _Guiones(Flowable):
    """El renglón de guiones que separa los bloques del tiquete."""

    def __init__(self, espacio=2 * mm):
        super().__init__()
        self.espacio = espacio

    def wrap(self, ancho_disponible, alto_disponible):
        self.width = ancho_disponible
        self.height = 2 * self.espacio
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setStrokeColor(_GRIS_GUION)
        canvas.setLineWidth(0.6)
        canvas.setDash(2, 2)
        canvas.line(0, self.espacio, self.width, self.espacio)
        canvas.restoreState()


class FormatoDocumentoPos(FormatoBase):
    """
    Tiquete POS: empresa, datos de la venta, ítems, totales y bases por impuesto.

    A diferencia de la factura en hoja, los datos que faltan no dejan su renglón:
    el tiquete no tiene un alto que conservar y cada renglón vacío es papel.
    """

    rollo = True

    campo_informacion_superior = 'ven_pos_informacion_superior'
    campo_informacion_inferior = 'ven_pos_informacion_inferior'

    def construir(self):
        documento = self.documento
        estilos = self._estilos()
        configuracion = configuracion_actual()

        elementos = [
            *self._empresa(configuracion, estilos),
            Spacer(1, 2 * mm),
            *self._datos(documento, estilos),
            _Guiones(),
            self._detalles(documento, estilos),
            _Guiones(),
            self._totales(self._filas_total(documento), estilos),
            _Guiones(),
            self._totales(self._filas_base(documento), estilos),
        ]
        impuestos = self._impuestos(documento, estilos)
        if impuestos is not None:
            elementos += [_Guiones(), impuestos]
        elementos += self._electronico(documento, configuracion, estilos)
        elementos += self._pie(configuracion, estilos)
        return elementos

    # ------------------------------------------------------------- estilos ----

    @staticmethod
    def _estilos():
        base = getSampleStyleSheet()['Normal']

        def estilo(nombre, **kwargs):
            return ParagraphStyle(f'pos_{nombre}', parent=base, fontSize=8, leading=10.5, **kwargs)

        return {
            'razon_social': estilo('razon_social', fontName='Helvetica-Bold', alignment=TA_CENTER),
            'empresa': estilo('empresa', alignment=TA_CENTER),
            'dato': estilo('dato'),
            'columna': estilo('columna', fontName='Helvetica-Bold'),
            'columna_cifra': estilo('columna_cifra', fontName='Helvetica-Bold', alignment=TA_RIGHT),
            'celda': estilo('celda'),
            'cifra': estilo('cifra', alignment=TA_RIGHT),
            'total': estilo('total', fontName='Helvetica-Bold'),
            'total_cifra': estilo('total_cifra', fontName='Helvetica-Bold', alignment=TA_RIGHT),
            'centro': estilo('centro', alignment=TA_CENTER),
            'pie': estilo('pie', fontName='Helvetica-Bold', alignment=TA_CENTER),
            'cufe': ParagraphStyle(
                'pos_cufe', parent=base, fontName='Courier-Bold', fontSize=6.5, leading=8,
            ),
        }

    # ------------------------------------------------------------ utilidades ----

    @staticmethod
    def _texto(valor):
        """El valor escapado para `Paragraph`: una razón social con «&» rompería el tiquete."""
        return '' if valor is None else escape(str(valor))

    @staticmethod
    def _moneda(valor):
        return f'{valor or CERO:,.0f}'

    @staticmethod
    def _cantidad(valor):
        """«1», «2.5»: sin los ceros que trae el decimal de seis posiciones."""
        return f'{(valor or CERO).normalize():f}'

    @staticmethod
    def _numero(documento):
        """«FEPS1284»: el prefijo de la resolución pegado al número, como lo numera la DIAN."""
        if documento.numero is None:
            return ''
        prefijo = documento.resolucion.prefijo if documento.resolucion_id else ''
        return f'{prefijo or ""}{documento.numero}'

    def _informacion(self, configuracion, campo, estilos):
        """El texto libre de la configuración, centrado y con sus saltos de línea."""
        texto = (getattr(configuracion, campo, None) or '').strip()
        if not texto:
            return []
        return [
            Spacer(1, 1.5 * mm),
            Paragraph('<br/>'.join(self._texto(linea) for linea in texto.splitlines()),
                      estilos['centro']),
        ]

    # ------------------------------------------------------------ encabezado ----

    def _empresa(self, configuracion, estilos):
        """Razón social, NIT, dirección con la ciudad y teléfono, centrados."""
        empresa = datos_empresa(configuracion)
        ciudad = getattr(configuracion, 'gen_empresa_ciudad', None)
        direccion = ' - '.join(
            parte for parte in (empresa['direccion'], ciudad and ciudad.nombre.upper()) if parte
        )
        lineas = (
            f'NIT: {empresa["nit"]}' if empresa['nit'] else '',
            direccion,
            f'Tel: {empresa["telefono"]}' if empresa['telefono'] else '',
        )
        return [
            Paragraph(self._texto(empresa['razon_social'].upper()), estilos['razon_social']),
            *(Paragraph(self._texto(linea), estilos['empresa']) for linea in lineas if linea),
            *self._informacion(configuracion, self.campo_informacion_superior, estilos),
        ]

    def _datos(self, documento, estilos):
        """Número, fecha, cómo se paga y a quién se le vende."""
        contacto = documento.contacto
        plazo = documento.plazo_pago
        credito = bool(plazo and plazo.dias > 0)
        pares = (
            ('Número', self._numero(documento)),
            ('Fecha', documento.fecha and documento.fecha.strftime('%Y/%m/%d')),
            ('Forma de pago', 'Crédito' if credito else 'Contado'),
            ('Medio de pago', documento.metodo_pago and documento.metodo_pago.nombre),
            ('Cliente', contacto and contacto.nombre_corto),
            ('Nit/C.C', contacto and contacto.numero_identificacion),
            ('Dirección', contacto and contacto.direccion),
            ('Teléfono', contacto and contacto.telefono),
        )
        # El número sale aunque falte: un tiquete sin número tiene que verse así.
        return [
            Paragraph(f'{etiqueta}: {self._texto(valor)}', estilos['dato'])
            for etiqueta, valor in pares
            if valor or etiqueta == 'Número'
        ]

    # -------------------------------------------------------------- detalles ----

    @staticmethod
    def _lineas(documento):
        """Solo las líneas de ítem: un tiquete no lleva apuntes contables."""
        return [
            detalle for detalle in documento.documentos_detalles_documento_rel.all()
            if detalle.item_id
        ]

    def _detalles(self, documento, estilos):
        """
        Cada ítem con sus impuestos entre paréntesis —«CAFÉ (IVA 19%)»—, la cantidad
        y el subtotal antes de impuestos.
        """
        filas = [[
            Paragraph('Ítem', estilos['columna']),
            Paragraph('Cant', estilos['columna_cifra']),
            Paragraph('Subtotal', estilos['columna_cifra']),
        ]]
        for detalle in self._lineas(documento):
            impuestos = ', '.join(
                impuesto.impuesto.nombre
                for impuesto in detalle.documentos_impuestos_documento_detalle_rel.all()
            )
            descripcion = self._texto(detalle.detalle or detalle.item.nombre)
            if impuestos:
                descripcion = f'{descripcion} ({self._texto(impuestos)})'
            filas.append([
                Paragraph(descripcion, estilos['celda']),
                Paragraph(self._cantidad(detalle.cantidad), estilos['cifra']),
                Paragraph(self._moneda(detalle.subtotal), estilos['cifra']),
            ])

        tabla = Table(filas, colWidths=_ANCHO_DETALLES, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ]))
        return tabla

    # --------------------------------------------------------------- totales ----

    def _filas_total(self, documento):
        return (
            ('Total', self._moneda(documento.total)),
            ('Total items', str(len(self._lineas(documento)))),
        )

    def _filas_base(self, documento):
        """
        Lo que se vendió antes de impuestos y lo que suman. El descuento solo
        sale si lo hay: en caja casi nunca, y un «Descuento: 0» es ruido.
        """
        descuento = documento.descuento or CERO
        filas = [('Vta antes de impuestos', self._moneda((documento.subtotal or CERO) - descuento))]
        if descuento:
            filas.insert(0, ('Descuento', self._moneda(descuento)))
        filas.append(('Impuestos', self._moneda(documento.impuesto)))
        return filas

    @staticmethod
    def _totales(filas, estilos):
        tabla = Table(
            [[Paragraph(f'{etiqueta}:', estilos['total']), Paragraph(valor, estilos['total_cifra'])]
             for etiqueta, valor in filas],
            colWidths=_ANCHO_TOTALES,
        )
        tabla.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        return tabla

    def _impuestos(self, documento, estilos):
        """
        Un renglón por impuesto con su base y su valor: primero los que se cobran
        y después las retenciones. Sin impuestos no sale el bloque.
        """
        filas = [
            [Paragraph(self._texto(fila['impuesto__nombre_extendido']), estilos['celda']),
             Paragraph(self._moneda(fila['base']), estilos['cifra']),
             Paragraph(self._moneda(fila['valor']), estilos['cifra'])]
            for fila in GenDocumentoImpuesto.objects
            .filter(documento_detalle__documento=documento)
            .values('impuesto_id', 'impuesto__nombre_extendido', 'impuesto__operacion')
            .annotate(base=Sum('base'), valor=Sum('total'))
            .order_by('-impuesto__operacion', 'impuesto_id')
        ]
        if not filas:
            return None
        filas.insert(0, [
            Paragraph('Descripción', estilos['columna']),
            Paragraph('Vr base', estilos['columna_cifra']),
            Paragraph('Vr impto', estilos['columna_cifra']),
        ])
        tabla = Table(filas, colWidths=_ANCHO_IMPUESTOS)
        tabla.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        return tabla

    # ------------------------------------------------------------------- pie ----

    def _electronico(self, documento, configuracion, estilos):
        """El POS no electrónico no lleva nada ante la DIAN."""
        return []

    def _pie(self, configuracion, estilos):
        """El texto libre de la empresa y con qué software se generó el tiquete."""
        return [
            _Guiones(),
            *self._informacion(configuracion, self.campo_informacion_inferior, estilos),
            Spacer(1, 2 * mm),
            Paragraph(self._texto(f'{SOFTWARE} · {MODALIDAD_SOFTWARE}'), estilos['pie']),
            Paragraph(self._texto(FABRICANTE_SOFTWARE), estilos['pie']),
        ]


class FormatoDocumentoPosElectronico(FormatoDocumentoPos):
    """
    Tiquete POS electrónico: el mismo tiquete y, antes del pie, la resolución, el
    CUFE, la fecha de validación y el QR.

    Sin CUFE el documento no está validado: en su lugar sale el aviso, y el QR
    lleva los datos del documento sin nada que lo haga pasar por válido, igual
    que en la factura electrónica.
    """

    def _electronico(self, documento, configuracion, estilos):
        resolucion = documento.resolucion
        elementos = [_Guiones()]
        if resolucion is not None:
            elementos += [
                Paragraph(
                    f'Resolución: {self._texto(resolucion.numero)} {self._texto(resolucion.fecha_desde)}',
                    estilos['dato'],
                ),
                Paragraph(
                    f'Prefijo: {self._texto(resolucion.prefijo) or "sin prefijo"} del '
                    f'{resolucion.consecutivo_desde} al {resolucion.consecutivo_hasta}',
                    estilos['dato'],
                ),
                Paragraph(f'Vigente hasta: {self._texto(resolucion.fecha_hasta)}', estilos['dato']),
                _Guiones(),
            ]

        cufe = documento.cue
        if cufe:
            renglones = [cufe[i:i + _CARACTERES_CUFE] for i in range(0, len(cufe), _CARACTERES_CUFE)]
            elementos.append(Paragraph(
                'CUFE:<br/>' + '<br/>'.join(escape(renglon) for renglon in renglones), estilos['cufe'],
            ))
        else:
            elementos.append(Paragraph(
                '<b>DOCUMENTO SIN VALIDAR ANTE LA DIAN: todavía no tiene CUFE.</b>', estilos['dato'],
            ))
        if documento.fecha_validacion:
            validacion = timezone.localtime(documento.fecha_validacion).strftime('%Y-%m-%d %H:%M:%S')
            elementos += [
                Spacer(1, 1.5 * mm),
                Paragraph(f'<b>Fecha validación DIAN:</b> {validacion}', estilos['dato']),
            ]

        qr = dibujo_qr(FormatoDocumentoFactura.contenido_qr(documento, configuracion), LADO_QR)
        qr.hAlign = 'CENTER'
        elementos += [Spacer(1, 3 * mm), qr]
        return elementos
