"""
Facturación electrónica con rededoc: creación del emisor, carga del certificado y
emisión de documentos.

El flujo es front → back → rededoc. El front solo dispara la acción: el payload
lo arma el back leyendo `GenConfiguracion`, nunca lo que mande el navegador. Si
el NIT y la razón social vinieran del front, un cliente podría registrar un
emisor a nombre de otra empresa.

El emisor queda en `GenParametro`, que es de solo lectura para el tenant: es un
hecho verificado contra rededoc, no algo que el cliente afirme. Crear el emisor
no activa la facturación electrónica; `gen_factura_electronica_activa` se maneja
aparte.
"""

from decimal import ROUND_HALF_UP, Decimal

from rest_framework.exceptions import NotFound, ValidationError

from general.models import GenConfiguracion, GenDocumento, GenParametro
from general.servicios.documento import DOCUMENTO_CLASE_FACTURA_VENTA
from general.servicios.rededoc import Rededoc
from utilidades.excepciones import con_detail

EXTENSIONES_CERTIFICADO = ('.p12', '.pfx')
TAMANO_MAXIMO_CERTIFICADO = 1024 * 1024  # 1 MB; un certificado real pesa unos pocos KB


class ErrorFacturaElectronica(Exception):
    """
    Falla esperable de la activación. La vista la traduce a una respuesta HTTP.

    `cuerpo` es lo que sale en la respuesta: un texto nuestro se envuelve en
    `detail`, y el cuerpo de error de rededoc pasa sin envolver —envolverlo dejaba
    al front con el error anidado dentro del error—. Si rededoc no trae `detail`
    (un error por campo, por ejemplo), `con_detail` lo completa con su primer
    mensaje sin quitar nada.
    """

    def __init__(self, cuerpo, status=400):
        super().__init__(cuerpo)
        self.cuerpo = con_detail(cuerpo)
        self.status = status


def crear_emisor(cliente: Rededoc = None) -> GenParametro:
    """
    Crea el emisor del tenant en rededoc y guarda su id en `GenParametro`.

    No se consulta antes si el NIT ya tiene emisor: la unicidad la valida rededoc,
    que es quien la conoce. Si ya está registrado, rededoc rechaza la creación y
    ese mensaje es el que sube al front.
    """
    cliente = cliente or Rededoc()
    configuracion, _ = GenConfiguracion.objects.get_or_create(id=1)

    # Los campos que rededoc exige, en el orden en que aparecen en el payload. Se
    # nombra el que falta para que el usuario sepa qué llenar en configuración.
    if not configuracion.gen_empresa_razon_social:
        raise ErrorFacturaElectronica('Falta la razón social de la empresa.')
    if not configuracion.gen_empresa_numero_identificacion:
        raise ErrorFacturaElectronica('Falta el número de identificación de la empresa.')
    if not configuracion.gen_empresa_identificacion:
        raise ErrorFacturaElectronica('Falta el tipo de identificación de la empresa.')
    if not configuracion.gen_empresa_tipo_persona:
        raise ErrorFacturaElectronica('Falta el tipo de organización de la empresa.')
    if not configuracion.gen_empresa_ciudad:
        raise ErrorFacturaElectronica('Falta la ciudad de la empresa.')
    if not configuracion.gen_empresa_direccion:
        raise ErrorFacturaElectronica('Falta la dirección de la empresa.')
 
    ciudad = configuracion.gen_empresa_ciudad
    estado = ciudad.estado
    pais = estado.pais

    payload = {
        'razon_social': configuracion.gen_empresa_razon_social,
        'nombre_comercial': configuracion.gen_empresa_nombre_corto,
        'tipo_identificacion': configuracion.gen_empresa_identificacion_id,
        'numero_identificacion': configuracion.gen_empresa_numero_identificacion,
        'digito_verificacion': configuracion.gen_empresa_digito_verificacion or '',
        'tipo_organizacion': configuracion.gen_empresa_tipo_persona_id,
        'pais': pais.codigo,
        'departamento': estado.codigo,
        'municipio': ciudad.codigo,
        'direccion': configuracion.gen_empresa_direccion,
        'telefono': configuracion.gen_empresa_telefono or '',
        'correo': configuracion.gen_empresa_correo or '',
    }

    respuesta = cliente.crear_emisor(payload)
    if respuesta['error']:
        # 502 cuando rededoc no respondió o falló por dentro; 400 cuando rechazó
        # los datos, que es algo que el usuario puede corregir en configuración
        # (o el emisor ya existe, y rededoc lo dice en su propio mensaje).
        status = 400 if 400 <= respuesta['status'] < 500 else 502
        raise ErrorFacturaElectronica(respuesta['datos'], status=status)
    emisor_id = (respuesta['datos'] or {}).get('id')

    parametro, _ = GenParametro.objects.get_or_create(id=1)
    parametro.gen_rededoc_emisor = emisor_id
    parametro.save(update_fields=['gen_rededoc_emisor'])
    return parametro


def cargar_certificado(archivo, clave, cliente: Rededoc = None) -> dict:
    """
    Manda a rededoc el certificado de firma del emisor y devuelve su respuesta.

    El archivo no se guarda de este lado ni pasa por B2: es la llave privada con
    la que se firman las facturas de la empresa, y quien la necesita para firmar
    es rededoc. Acá pasa por memoria, se reenvía y se olvida. La clave tampoco se
    persiste.
    """
    if archivo is None:
        raise ErrorFacturaElectronica('Falta el archivo del certificado.')
    if not clave:
        raise ErrorFacturaElectronica('Falta la clave del certificado.')

    nombre = archivo.name or ''
    if not nombre.lower().endswith(EXTENSIONES_CERTIFICADO):
        raise ErrorFacturaElectronica(
            'El certificado debe ser un archivo {}.'.format(' o '.join(EXTENSIONES_CERTIFICADO)),
        )
    if archivo.size > TAMANO_MAXIMO_CERTIFICADO:
        raise ErrorFacturaElectronica(
            'El certificado supera el límite de {} MB.'.format(TAMANO_MAXIMO_CERTIFICADO // (1024 * 1024)),
        )

    # El certificado se cuelga del emisor, así que sin emisor no hay dónde ponerlo.
    parametro, _ = GenParametro.objects.get_or_create(id=1)
    if not parametro.gen_rededoc_emisor:
        raise ErrorFacturaElectronica(
            'Primero hay que crear el emisor en el servicio de facturación electrónica.',
        )

    cliente = cliente or Rededoc()
    archivo.seek(0)
    respuesta = cliente.cargar_certificado(
        parametro.gen_rededoc_emisor, archivo, clave, nombre=nombre,
    )
    if respuesta['error']:
        status = 400 if 400 <= respuesta['status'] < 500 else 502
        raise ErrorFacturaElectronica(respuesta['datos'], status=status)

    datos = respuesta['datos'] or {}
    parametro.gen_certificado_vence = datos.get('vigente_hasta')
    parametro.save(update_fields=['gen_certificado_vence'])
    return datos


# --------------------------------------------------------------- emitir ----
#
# Cada clase de documento arma su propio payload para rededoc. Lo que no está en
# `ARMADORES` no se emite todavía, y se rechaza antes de enviar nada.
#
# Tipo de identificación, país, departamento y municipio viajan con el id de
# torio, que rededoc recibe como llave primaria de su catálogo. El resto de
# catálogos todavía va por código.

# Lo que torio todavía no modela y rededoc exige. Valores fijos mientras no haya
# de dónde sacarlos.
MONEDA = 35  # COP, id del catálogo de monedas de rededoc
UNIDAD_MEDIDA = '94'  # Unidad
MEDIO_PAGO_NO_DEFINIDO = '1'  # Instrumento no definido
FORMA_PAGO_CONTADO = '1'
FORMA_PAGO_CREDITO = '2'

# `GenImpuestoTipo.codigo` → código DIAN del tributo. Sin tipo, o con uno que no
# esté acá, el impuesto sale como IVA, que es lo que son todos los de venta que
# trae el fixture (ninguno tiene tipo).
TRIBUTOS = {'IVA': '01', 'ICA': '03', 'COM': '04'}
TRIBUTO_POR_DEFECTO = '01'

DOS_DECIMALES = Decimal('0.01')


def emitir(documento_ids, cliente: Rededoc = None) -> list:
    """
    Crea en rededoc cada documento y devuelve los ids de los que quedaron creados.

    Todo se valida y se arma antes de enviar el primero: un dato que falte en
    cualquiera de los documentos corta el lote sin haber mandado nada. El envío
    en cambio no es atómico —rededoc no deshace lo creado—, así que cada
    documento creado se marca apenas rededoc lo acepta, y si uno falla, los
    anteriores quedan marcados y el error dice cuáles fueron.
    """
    if not documento_ids:
        raise ValidationError({'ids': 'Este campo es requerido.'})

    parametro = GenParametro.objects.filter(id=1).first()
    if parametro is None or not parametro.gen_factura_electronica_activa:
        raise ErrorFacturaElectronica('La empresa no se ha activado para facturar electrónicamente.')
    if not parametro.gen_rededoc_emisor:
        raise ErrorFacturaElectronica('La empresa no tiene emisor en el servicio de facturación electrónica.')

    documentos = GenDocumento.objects.select_related(
        'documento_tipo', 'resolucion', 'plazo_pago', 'metodo_pago',
        'contacto__identificacion', 'contacto__ciudad__estado__pais',
    ).in_bulk(documento_ids)
    for documento_id in documento_ids:
        documento = documentos.get(documento_id)
        if documento is None:
            raise NotFound(f'El documento {documento_id} no existe.')
        if not documento.estado_aprobado:
            raise ErrorFacturaElectronica(f'El documento {documento_id} debe estar aprobado.')
        if documento.estado_electronico_enviado:
            raise ErrorFacturaElectronica(f'El documento {documento_id} ya fue enviado electrónicamente.')
        if documento.documento_tipo.documento_clase_id not in ARMADORES:
            raise ErrorFacturaElectronica(
                f'El documento {documento_id} es de un tipo que todavía no se emite electrónicamente.'
            )

    payloads = [
        (documentos[documento_id], _armar(documentos[documento_id], parametro))
        for documento_id in documento_ids
    ]

    cliente = cliente or Rededoc()
    emitidos = []
    for documento, payload in payloads:
        respuesta = cliente.crear_documento(payload)
        if respuesta['error']:
            status = 400 if 400 <= respuesta['status'] < 500 else 502
            raise ErrorFacturaElectronica(
                {
                    'detail': (
                        f'El servicio de facturación electrónica rechazó el documento {documento.id}.'
                    ),
                    'documento': documento.id,
                    'emitidos': emitidos,
                    'error': respuesta['datos'],
                },
                status=status,
            )
        documento.electronico_id = (respuesta['datos'] or {}).get('id')
        documento.estado_electronico_enviado = True
        documento.save(update_fields=['electronico_id', 'estado_electronico_enviado'])
        emitidos.append(documento.id)
    return emitidos


def _armar(documento, parametro):
    return ARMADORES[documento.documento_tipo.documento_clase_id](documento, parametro)


def _armar_factura_venta(documento, parametro):
    if documento.documento_tipo.codigo is None:
        raise ErrorFacturaElectronica(
            f'El tipo de documento {documento.documento_tipo.nombre} no tiene código de '
            'facturación electrónica.'
        )
    if documento.resolucion is None:
        raise ErrorFacturaElectronica(f'El documento {documento.id} no tiene resolución.')
    if documento.numero is None:
        raise ErrorFacturaElectronica(f'El documento {documento.id} no tiene número.')
    if documento.fecha is None:
        raise ErrorFacturaElectronica(f'El documento {documento.id} no tiene fecha.')

    resolucion = documento.resolucion
    if not (resolucion.consecutivo_desde <= documento.numero <= resolucion.consecutivo_hasta):
        raise ErrorFacturaElectronica(
            f'El número {documento.numero} del documento {documento.id} está fuera del rango '
            f'de la resolución, que va desde {resolucion.consecutivo_desde} hasta '
            f'{resolucion.consecutivo_hasta}.'
        )
    if not (resolucion.fecha_desde <= documento.fecha <= resolucion.fecha_hasta):
        raise ErrorFacturaElectronica(
            f'La fecha {documento.fecha} del documento {documento.id} está fuera de la vigencia '
            f'de la resolución, que va desde {resolucion.fecha_desde} hasta {resolucion.fecha_hasta}.'
        )

    credito = bool(documento.plazo_pago and documento.plazo_pago.dias > 0)
    if credito and documento.fecha_vence is None:
        raise ErrorFacturaElectronica(
            f'El documento {documento.id} es a crédito y no tiene fecha de vencimiento.'
        )

    return {
        'emisor': parametro.gen_rededoc_emisor,
        'documento_tipo': documento.documento_tipo.codigo,
        'prefijo': documento.resolucion.prefijo or '',
        'numero_resolucion': documento.resolucion.numero,
        'consecutivo': documento.numero,
        'fecha_emision': documento.fecha.isoformat(),
        'fecha_vencimiento': documento.fecha_vence.isoformat() if credito else None,
        'forma_pago': FORMA_PAGO_CREDITO if credito else FORMA_PAGO_CONTADO,
        'medio_pago': getattr(documento.metodo_pago, 'codigo', None) or MEDIO_PAGO_NO_DEFINIDO,
        'moneda': MONEDA,
        'adquiriente': _adquiriente(documento),
        'detalles': _detalles(documento),
    }


def _adquiriente(documento):
    contacto = documento.contacto
    if contacto is None:
        raise ErrorFacturaElectronica(f'El documento {documento.id} no tiene cliente.')

    ciudad = contacto.ciudad
    codigo_postal = contacto.codigo_postal or ciudad.codigo_postal
    if not codigo_postal:
        raise ErrorFacturaElectronica(
            f'El cliente {contacto.nombre_corto} no tiene código postal, ni su ciudad uno por defecto.'
        )

    return {
        'tipo_identificacion': contacto.identificacion_id,
        'numero_identificacion': contacto.numero_identificacion,
        'razon_social': contacto.nombre_corto,
        'primer_nombre': contacto.nombre1 or '',
        'segundo_nombre': contacto.nombre2 or '',
        'primer_apellido': contacto.apellido1 or '',
        'segundo_apellido': contacto.apellido2 or '',
        # Los ids de `GenTipoPersona` coinciden con la lista TipoOrganizacion de
        # la DIAN: 1 jurídica, 2 natural.
        'tipo_organizacion': str(contacto.tipo_persona_id),
        # Vacía sale como R-99-PN («No responsable»).
        'responsabilidades': [],
        'pais': ciudad.estado.pais_id,
        'departamento': ciudad.estado_id,
        'municipio': ciudad.id,
        'direccion': contacto.direccion,
        'telefono': contacto.telefono,
        'correo': contacto.correo_facturacion_electronica or contacto.correo,
        'codigo_postal': codigo_postal,
    }


def _detalles(documento):
    lineas = (
        documento.documentos_detalles_documento_rel
        .filter(item__isnull=False)
        .select_related('item')
        .prefetch_related('documentos_impuestos_documento_detalle_rel__impuesto__impuesto_tipo')
        .order_by('id')
    )
    detalles = []
    for numero_linea, linea in enumerate(lineas, start=1):
        detalles.append({
            'codigo_producto': linea.item.codigo or str(linea.item.id),
            'numero_linea': numero_linea,
            'descripcion': linea.detalle or linea.item.nombre,
            'unidad_medida': UNIDAD_MEDIDA,
            'cantidad': _decimal(linea.cantidad),
            'descuento': _decimal(linea.descuento),
            'valor_unitario': _decimal(linea.precio),
            'valor_total': _decimal(linea.total_bruto),
            'impuestos': _impuestos(linea),
        })
    if not detalles:
        raise ErrorFacturaElectronica(f'El documento {documento.id} no tiene detalles para emitir.')
    return detalles


def _impuestos(linea):
    # Las retenciones (operación negativa) no van: en la factura rededoc las
    # rechaza, porque no las separa del total a pagar.
    return [
        {
            'tributo': TRIBUTOS.get(
                getattr(impuesto.impuesto.impuesto_tipo, 'codigo', None), TRIBUTO_POR_DEFECTO,
            ),
            'base_gravable': _decimal(impuesto.base),
            'tarifa': _decimal(impuesto.porcentaje),
            'valor': _decimal(impuesto.total),
        }
        for impuesto in linea.documentos_impuestos_documento_detalle_rel.all()
        if impuesto.impuesto.operacion > 0
    ]


def _decimal(valor):
    return str((valor or Decimal('0')).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP))


ARMADORES = {
    DOCUMENTO_CLASE_FACTURA_VENTA: _armar_factura_venta,
}
