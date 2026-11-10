"""
Informe de cierre de turno (cuadre de caja), en el rollo de 80 mm del tiquete POS.

Se lee de arriba a abajo: empresa, título, datos del turno, lo vendido, el arqueo
por cuenta bancaria, los totales y las firmas. Hereda del tiquete los estilos, el
encabezado de la empresa y los renglones de guiones, para que los dos papeles que
salen de la misma impresora se vean iguales.

Un turno abierto se imprime como **pre-cierre**: lo esperado por cuenta, sin
contado ni diferencia, que es lo que el cajero tiene que contar. Lo esperado se
calcula en el momento y puede cambiar mientras el turno siga recibiendo ventas;
el de un turno cerrado sale de lo guardado al cierre.
"""
from decimal import Decimal

from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table

from general.formatos.documento_pos import (
    _ANCHO_DATOS,
    _ANCHO_TOTALES,
    _ESTILO_TABLA,
    FormatoDocumentoPos,
    _Guiones,
)
from general.models import GenCuentaBanco, GenDocumento
from seguridad.cuenta import nombre_de_usuario
from utilidades.formatos import configuracion_actual
from venta.servicios import turno as turno_servicio

CERO = Decimal('0')


class FormatoTurnoCierre(FormatoDocumentoPos):
    """Recibe un `VenTurno` en vez de un documento; el resto del contrato de `FormatoBase` no cambia."""

    rollo = True

    # El cierre es un papel interno de la caja: no lleva el texto libre que la
    # empresa le pone al tiquete del cliente.
    campo_informacion_superior = None
    campo_informacion_inferior = None

    def __init__(self, turno):
        super().__init__(turno)
        self.turno = turno

    def construir(self):
        turno = self.turno
        estilos = self._estilos()
        configuracion = configuracion_actual()

        elementos = [
            *self._empresa(configuracion, estilos),
            _Guiones(),
            Paragraph(self._titulo_turno(turno), estilos['titulo']),
            *self._aviso_turno(turno, estilos),
            _Guiones(),
            self._datos_turno(turno, estilos),
            _Guiones(),
            *self._ventas(turno, estilos),
            _Guiones(),
            Paragraph('ARQUEO', estilos['columna']),
            Spacer(1, 1 * mm),
            *self._arqueo(turno, estilos),
        ]
        elementos += self._comentario(turno, estilos)
        elementos += self._firmas(turno, estilos)
        elementos += self._pie(configuracion, estilos)
        return elementos

    def _informacion(self, configuracion, campo, estilos):
        if not campo:
            return []
        return super()._informacion(configuracion, campo, estilos)

    # ------------------------------------------------------------ utilidades ----

    @staticmethod
    def _fecha_hora(valor):
        return timezone.localtime(valor).strftime('%Y/%m/%d %H:%M') if valor else ''

    def _tabla(self, pares, estilos, anchos=_ANCHO_DATOS, estilo_valor='dato'):
        tabla = Table(
            [[Paragraph(f'{etiqueta}:', estilos['etiqueta']), Paragraph(self._texto(valor), estilos[estilo_valor])]
             for etiqueta, valor in pares if valor not in (None, '')],
            colWidths=anchos,
        )
        tabla.setStyle(_ESTILO_TABLA)
        return tabla

    # ------------------------------------------------------------ encabezado ----

    @staticmethod
    def _titulo_turno(turno):
        titulo = 'CIERRE DE TURNO' if turno.estado_cerrado else 'PRE-CIERRE DE TURNO'
        return f'{titulo} N° {turno.id}'

    def _aviso_turno(self, turno, estilos):
        if turno.estado_cerrado:
            return []
        return [
            Spacer(1, 1 * mm),
            Paragraph(
                self._texto('Turno abierto: lo esperado puede cambiar mientras siga recibiendo ventas.'),
                estilos['aviso'],
            ),
        ]

    def _datos_turno(self, turno, estilos):
        return self._tabla((
            ('Caja', turno.caja.nombre),
            ('Sede', turno.caja.sede.nombre),
            ('Cajero', nombre_de_usuario(turno.usuario)),
            ('Apertura', self._fecha_hora(turno.fecha_apertura)),
            ('Cierre', self._fecha_hora(turno.fecha_cierre)),
            ('Base', self._moneda(turno.base)),
            ('Base en', turno.cuenta_banco.nombre if turno.cuenta_banco_id else None),
        ), estilos)

    # ---------------------------------------------------------------- ventas ----

    def _ventas(self, turno, estilos):
        """Cuántas facturas, el rango de numeración, las anuladas y el total vendido."""
        facturas = list(
            GenDocumento.objects
            .filter(turno=turno)
            .select_related('resolucion')
            .order_by('numero', 'id')
        )
        validas = [f for f in facturas if not f.estado_anulado]
        numeradas = [f for f in validas if f.numero is not None]
        if turno.estado_cerrado:
            total, cantidad = turno.total_venta, turno.cantidad_documentos
        else:
            total, cantidad = turno_servicio.totales(turno)

        tabla = self._tabla((
            ('Facturas', str(cantidad)),
            ('Desde', self._numero(numeradas[0]) if numeradas else None),
            ('Hasta', self._numero(numeradas[-1]) if numeradas else None),
            ('Anuladas', str(len(facturas) - len(validas)) if len(facturas) > len(validas) else None),
        ), estilos)
        total_tabla = self._tabla(
            (('TOTAL VENTA', self._moneda(total)),), estilos, anchos=_ANCHO_TOTALES, estilo_valor='total_cifra',
        )
        return [tabla, Spacer(1, 1 * mm), total_tabla]

    # ---------------------------------------------------------------- arqueo ----

    def _cuentas(self, turno):
        """[(nombre, esperado, contado, diferencia)] por cuenta; contado y diferencia en None si está abierto."""
        if turno.estado_cerrado:
            return [
                (d.cuenta_banco.nombre, d.esperado, d.contado, d.diferencia)
                for d in turno.turnos_detalles_turno_rel.select_related('cuenta_banco').order_by('cuenta_banco__nombre')
            ]
        esperados = turno_servicio.esperado(turno)
        nombres = dict(GenCuentaBanco.objects.filter(id__in=esperados).values_list('id', 'nombre'))
        return sorted(
            ((nombres[cuenta_id], valor, None, None) for cuenta_id, valor in esperados.items()),
            key=lambda fila: fila[0],
        )

    def _arqueo(self, turno, estilos):
        """
        Dos o más renglones por cuenta, como los ítems del tiquete: el nombre a todo
        el ancho y debajo esperado, contado y diferencia. Cuatro columnas no caben en
        72 mm sin pegar las cifras.
        """
        cuentas = self._cuentas(turno)
        if not cuentas:
            return [Paragraph(self._texto('Sin pagos registrados.'), estilos['dato'])]

        elementos = []
        for nombre, esperado, contado, diferencia in cuentas:
            elementos.append(Paragraph(self._texto(nombre), estilos['etiqueta']))
            pares = [('Esperado', esperado)]
            if turno.estado_cerrado:
                pares += [('Contado', contado), ('Diferencia', diferencia)]
            tabla = Table(
                [[Paragraph(etiqueta, estilos['linea']), Paragraph(self._moneda(valor), estilos['cifra'])]
                 for etiqueta, valor in pares],
                colWidths=_ANCHO_TOTALES,
            )
            tabla.setStyle(_ESTILO_TABLA)
            elementos += [tabla, Spacer(1, 1 * mm)]

        total_esperado = sum((fila[1] for fila in cuentas), CERO)
        totales = [('TOTAL ESPERADO', total_esperado)]
        if turno.estado_cerrado:
            total_contado = sum((fila[2] for fila in cuentas), CERO)
            totales += [('TOTAL CONTADO', total_contado), ('DIFERENCIA', total_contado - total_esperado)]
        tabla = Table(
            [[Paragraph(etiqueta, estilos['total']), Paragraph(self._moneda(valor), estilos['total_cifra'])]
             for etiqueta, valor in totales],
            colWidths=_ANCHO_TOTALES,
        )
        tabla.setStyle(_ESTILO_TABLA)
        return [*elementos, _Guiones(), tabla]

    # ------------------------------------------------------------------- pie ----

    def _comentario(self, turno, estilos):
        if not turno.comentario:
            return []
        return [
            _Guiones(),
            Paragraph('Observaciones:', estilos['etiqueta']),
            Paragraph(self._texto(turno.comentario), estilos['dato']),
        ]

    def _firmas(self, turno, estilos):
        """El cierre se firma: quien entrega la caja y quien la recibe."""
        if not turno.estado_cerrado:
            return []
        return [
            _Guiones(),
            Spacer(1, 10 * mm),
            Paragraph('_' * 32, estilos['centro']),
            Paragraph('Firma cajero', estilos['centro']),
            Spacer(1, 10 * mm),
            Paragraph('_' * 32, estilos['centro']),
            Paragraph('Firma supervisor', estilos['centro']),
        ]
