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

from django.db import connection
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from general.models import GenConfiguracion, GenDocumento, GenParametro
from general.servicios.documento import DOCUMENTO_CLASE_FACTURA_VENTA
from general.servicios.rededoc import Rededoc
from utilidades.excepciones import con_detail

EXTENSIONES_CERTIFICADO = ('.p12', '.pfx')
TAMANO_MAXIMO_CERTIFICADO = 1024 * 1024  # 1 MB; un certificado real pesa unos pocos KB
MODULOS_SOFTWARE = ('facturacion', 'nomina')


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


def _emisor_id() -> int:
    """El id del emisor del tenant en rededoc; 404 si no tiene emisor configurado."""
    parametro, _ = GenParametro.objects.get_or_create(id=1)
    if not parametro.gen_rededoc_emisor:
        raise ErrorFacturaElectronica(
            'La empresa no tiene emisor configurado en el servicio de facturación electrónica.',
            status=404,
        )
    return parametro.gen_rededoc_emisor


def _error_rededoc(respuesta):
    """
    502 cuando rededoc no respondió o falló por dentro; 400 cuando rechazó los
    datos, que es algo que el usuario puede corregir.
    """
    status = 400 if 400 <= respuesta['status'] < 500 else 502
    return ErrorFacturaElectronica(respuesta['datos'], status=status)


def _datos_actualizables(configuracion: GenConfiguracion) -> dict:
    """
    Los campos del emisor que rededoc deja cambiar, leídos de `GenConfiguracion`.
    Los usan el alta y la actualización, para que las dos manden lo mismo.

    Se nombra el que falta para que el usuario sepa qué llenar en configuración.
    """
    if not configuracion.gen_empresa_razon_social:
        raise ErrorFacturaElectronica('Falta la razón social de la empresa.')
    if not configuracion.gen_empresa_tipo_persona:
        raise ErrorFacturaElectronica('Falta el tipo de organización de la empresa.')
    if not configuracion.gen_empresa_direccion:
        raise ErrorFacturaElectronica('Falta la dirección de la empresa.')
    if not configuracion.gen_empresa_ciudad:
        raise ErrorFacturaElectronica('Falta la ciudad de la empresa.')
    if not configuracion.gen_empresa_correo:
        raise ErrorFacturaElectronica('Falta el correo de la empresa.')

    ciudad = configuracion.gen_empresa_ciudad
    estado = ciudad.estado
    return {
        'razon_social': configuracion.gen_empresa_razon_social,
        'tipo_organizacion': configuracion.gen_empresa_tipo_persona_id,
        'direccion': configuracion.gen_empresa_direccion,
        # País, departamento y municipio van por id: rededoc usa el mismo
        # catálogo geográfico que torio.
        'pais': estado.pais_id,
        'departamento': estado.id,
        'municipio': ciudad.id,
        'correo': configuracion.gen_empresa_correo,
    }


def emisor_crear(cliente: Rededoc = None) -> GenParametro:
    """
    Crea el emisor del tenant en rededoc y guarda su id en `GenParametro`.

    Si el tenant ya tiene un emisor guardado no se llama a rededoc: para crear
    otro primero hay que desvincular el actual. Lo que no se consulta es si el
    NIT ya tiene emisor en rededoc: esa unicidad la valida rededoc, que es quien
    la conoce, y su mensaje es el que sube al front.
    """
    parametro, _ = GenParametro.objects.get_or_create(id=1)
    if parametro.gen_rededoc_emisor:
        raise ErrorFacturaElectronica('El emisor ya está registrado.')

    cliente = cliente or Rededoc()
    configuracion, _ = GenConfiguracion.objects.get_or_create(id=1)

    # La identificación se fija en el alta y rededoc no deja cambiarla después,
    # por eso no está en `_datos_actualizables`.
    if not configuracion.gen_empresa_identificacion:
        raise ErrorFacturaElectronica('Falta el tipo de identificación de la empresa.')
    if not configuracion.gen_empresa_numero_identificacion:
        raise ErrorFacturaElectronica('Falta el número de identificación de la empresa.')

    payload = {
        'cuenta': 1,
        # El tipo de identificación va por su código DIAN (NIT = 31), que en
        # rededoc es también su id.
        'tipo_identificacion': int(configuracion.gen_empresa_identificacion.codigo),
        'numero_identificacion': configuracion.gen_empresa_numero_identificacion,
        **_datos_actualizables(configuracion),
        'telefono': configuracion.gen_empresa_telefono or '',
        # El tenant de torio. Rededoc lo guarda en el emisor y lo devuelve como
        # `cliente` en cada aviso del webhook: es como el webhook sabe a qué
        # schema entrar (ver docs/webhook_rededoc.md §5).
        'referencia_externa': str(connection.tenant.id),
    }

    respuesta = cliente.crear_emisor(payload)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    emisor_id = (respuesta['datos'] or {}).get('id')

    parametro.gen_rededoc_emisor = emisor_id
    parametro.save(update_fields=['gen_rededoc_emisor'])
    return parametro


def emisor_consultar(cliente: Rededoc = None) -> dict:
    """El emisor de `gen_rededoc_emisor` tal como lo tiene rededoc."""
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_emisor(emisor_id)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def emisor_actualizar(cliente: Rededoc = None) -> dict:
    """
    Manda a rededoc el PATCH del emisor de `gen_rededoc_emisor` con los campos
    actualizables de `GenConfiguracion`, igual que el alta, y devuelve el emisor
    actualizado.
    """
    emisor_id = _emisor_id()
    configuracion, _ = GenConfiguracion.objects.get_or_create(id=1)
    payload = _datos_actualizables(configuracion)

    cliente = cliente or Rededoc()
    respuesta = cliente.actualizar_emisor(emisor_id, payload)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def emisor_reasignar(emisor_id: int, cliente: Rededoc = None) -> GenParametro:
    """
    Asocia al tenant un emisor que ya existe en rededoc, guardándolo en
    `gen_rededoc_emisor`.

    Todos los emisores cuelgan de la misma API key de torio, así que el id solo
    no prueba nada: se asigna únicamente si en rededoc su `referencia_externa`
    es este tenant. Si no, el emisor de otra empresa quedaría a un número
    adivinado de distancia. Que no exista y que sea ajeno responden lo mismo,
    para no revelar qué emisores hay.
    """
    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_emisor(emisor_id)
    if respuesta['error'] and respuesta['status'] != 404:
        raise _error_rededoc(respuesta)
    referencia = None if respuesta['error'] else (respuesta['datos'] or {}).get('referencia_externa')
    if referencia is None or str(referencia) != str(connection.tenant.id):
        raise ErrorFacturaElectronica('El emisor no existe o no pertenece a esta empresa.')

    parametro, _ = GenParametro.objects.get_or_create(id=1)
    parametro.gen_rededoc_emisor = emisor_id
    parametro.save(update_fields=['gen_rededoc_emisor'])
    return parametro


def emisor_desvincular() -> GenParametro:
    """
    Borra `gen_rededoc_emisor`. El emisor sigue existiendo en rededoc: solo deja
    de estar asociado a este tenant, y con eso se puede volver a crear uno.
    """
    parametro, _ = GenParametro.objects.get_or_create(id=1)
    if not parametro.gen_rededoc_emisor:
        raise ErrorFacturaElectronica(
            'La empresa no tiene emisor configurado en el servicio de facturación electrónica.',
            status=404,
        )
    parametro.gen_rededoc_emisor = None
    parametro.save(update_fields=['gen_rededoc_emisor'])
    return parametro


def certificado_consultar(cliente: Rededoc = None) -> dict:
    """Los certificados del emisor de `gen_rededoc_emisor`, tal como los tiene rededoc."""
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_certificados(emisor_id)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def software_consultar(modulo: str = None, cliente: Rededoc = None) -> dict:
    """
    El software DIAN del emisor de `gen_rededoc_emisor`, tal como lo tiene
    rededoc. Con `modulo` (facturacion o nomina) solo el de ese módulo.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_software(emisor_id, modulo)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def software_crear(tipo: str, identificador: str, pin: str, test_set_id: str,
                   cliente: Rededoc = None) -> dict:
    """
    Registra en rededoc el software DIAN del emisor de `gen_rededoc_emisor`.

    En torio no se guarda nada: el software vive en rededoc y se lee con
    `software_consultar`. El PIN solo pasa de camino; rededoc no lo devuelve.
    Que el emisor ya tenga software de ese tipo, o que le falte el certificado,
    lo valida rededoc y su mensaje es el que sube al front.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.crear_software({
        'emisor': emisor_id,
        'tipo': tipo,
        'identificador': identificador,
        'pin': pin,
        'test_set_id': test_set_id,
    })
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def certificado_eliminar(cliente: Rededoc = None) -> GenParametro:
    """
    Borra en rededoc el certificado del emisor de `gen_rededoc_emisor`.

    El id del certificado no lo manda el front: se busca entre los del emisor
    guardado. Con la API key de torio se puede borrar el de cualquier emisor,
    así que aceptar un id del request dejaría a un tenant borrar el de otro.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()

    respuesta = cliente.consultar_certificados(emisor_id)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    # Rededoc pagina el listado; con un solo certificado por emisor cabe en la
    # primera página.
    certificados = (respuesta['datos'] or {}).get('results') or []
    if not certificados:
        raise ErrorFacturaElectronica('El emisor no tiene certificado cargado.', status=404)

    for certificado in certificados:
        respuesta = cliente.eliminar_certificado(certificado['id'])
        if respuesta['error']:
            raise _error_rededoc(respuesta)

    parametro = GenParametro.objects.get(id=1)
    parametro.gen_certificado_vence = None
    parametro.save(update_fields=['gen_certificado_vence'])
    return parametro


def certificado_cargar(archivo, clave, cliente: Rededoc = None) -> dict:
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
# Unidad (código DIAN 94). Va el id del catálogo de rededoc, no el código: rededoc
# convierte a entero lo que parece número y lo busca como id, y el id 94 es «pie
# cúbico por hora». El error no avisa, sale en la factura.
UNIDAD_MEDIDA = 70
MEDIO_PAGO_NO_DEFINIDO = '1'  # Instrumento no definido
FORMA_PAGO_CONTADO = '1'
FORMA_PAGO_CREDITO = '2'

# `GenImpuestoTipo.codigo` → código DIAN del tributo. Sin tipo, o con uno que no
# esté acá, el impuesto sale como IVA, que es lo que son todos los de venta que
# trae el catálogo (ninguno tiene tipo).
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
    parametro = _parametro_habilitado()

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


def _parametro_habilitado():
    """El `GenParametro` de una empresa que puede usar la facturación electrónica."""
    parametro = GenParametro.objects.filter(id=1).first()
    if parametro is None or not parametro.gen_factura_electronica_activa:
        raise ErrorFacturaElectronica('La empresa no se ha activado para facturar electrónicamente.')
    if not parametro.gen_rededoc_emisor:
        raise ErrorFacturaElectronica('La empresa no tiene emisor en el servicio de facturación electrónica.')
    return parametro


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


# ---------------------------------------------------------------- avisos ----
#
# Lo que rededoc avisa por el webhook (`contenedor.views.rededoc`). La vista ya
# entró al schema del tenant; acá solo se aplica el aviso al documento.

AVISO_VALIDACION = 'validacion'
AVISO_NOTIFICACION = 'notificacion'
AVISOS = (AVISO_VALIDACION, AVISO_NOTIFICACION)
# Para que rededoc confirme el secreto y la forma de firmar. No es de ningún
# documento: la vista lo responde apenas pasa la firma y nunca llega a
# `procesar_aviso`, por eso no va en `AVISOS`.
AVISO_PRUEBA = 'prueba'
# La DIAN habilitó al emisor para una operación. Tampoco es de un documento: lo
# aplica `procesar_habilitacion`, no `procesar_aviso`.
AVISO_HABILITACION = 'habilitacion'
# Operación de rededoc → campo de `GenParametro` que enciende.
CAMPO_HABILITADO_POR_OPERACION = {
    'facturacion': 'gen_electronico_habilitado_facturacion',
    'nomina': 'gen_electronico_habilitado_nomina',
    'documento_equivalente': 'gen_electronico_habilitado_equivalente',
}


class DocumentoYaValidado(APIException):
    """Un aviso de validación para un documento que ya estaba validado."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = 'El documento ya estaba validado.'
    default_code = 'documento_ya_validado'


def procesar_aviso(tipo, documento_id, fecha_validacion=None, cufe=None) -> GenDocumento:
    """
    Aplica un aviso de rededoc al documento cuyo `electronico_id` es `documento_id`.

    - `validacion`: la DIAN aceptó el documento; guarda su CUFE y la fecha, y
      programa su notificación al adquiriente (`general.tasks`). Si el documento ya
      estaba validado no se reescribe: responde 409, porque un CUFE no cambia, y
      uno distinto para el mismo documento es un error que hay que ver.
    - `notificacion`: el documento se le entregó al adquiriente. Repetirla deja el
      documento igual.
    """
    documento = GenDocumento.objects.filter(electronico_id=documento_id).first()
    if documento is None:
        raise NotFound('El documento no existe.')

    if tipo == AVISO_VALIDACION:
        if documento.estado_electronico:
            raise DocumentoYaValidado()
        documento.estado_electronico = True
        documento.fecha_validacion = fecha_validacion
        documento.cue = cufe
        documento.save(update_fields=['estado_electronico', 'fecha_validacion', 'cue'])
        # Validado, ya se le puede entregar al adquiriente. Va por la cola y no
        # acá: armar el PDF y esperar a rededoc y a su pasarela de correo no
        # tiene por qué demorar la respuesta del webhook.
        from general.tasks import programar_notificacion

        programar_notificacion(documento.id)
    else:
        documento.estado_electronico_notificado = True
        documento.save(update_fields=['estado_electronico_notificado'])
    return documento



def procesar_habilitacion(emisor_id, operacion) -> GenParametro:
    """
    Marca al tenant habilitado ante la DIAN para `operacion`.

    Solo enciende: apagar la bandera no es algo que avise rededoc. Repetir el
    aviso deja todo igual. El `emisor` tiene que ser el de `gen_rededoc_emisor`:
    un aviso tardío de un emisor ya desvinculado o reasignado no puede habilitar
    al tenant con lo que la DIAN aprobó para otro. Responde el mismo 404 que un
    cliente desconocido.
    """
    parametro, _ = GenParametro.objects.get_or_create(id=1)
    if not parametro.gen_rededoc_emisor or parametro.gen_rededoc_emisor != emisor_id:
        raise NotFound('El emisor no existe.')

    campo = CAMPO_HABILITADO_POR_OPERACION[operacion]
    setattr(parametro, campo, True)
    parametro.save(update_fields=[campo])
    return parametro

# ------------------------------------------------------------ notificar ----

def correo_notificacion(documento) -> str:
    """
    A dónde se le envía el documento al cliente, o `''` si no hay a dónde.

    El de facturación electrónica, que es el que el cliente eligió para recibir sus
    facturas; si no lo tiene, el correo general. Un contacto sin ninguno de los dos
    no se notifica: queda pendiente, a la vista en la pantalla de pendientes por
    notificar, hasta que alguien lo cargue.
    """
    contacto = documento.contacto
    if contacto is None:
        return ''
    return (contacto.correo_facturacion_electronica or '').strip() or (contacto.correo or '').strip()


def notificar(documento_ids, cliente: Rededoc = None) -> list:
    """
    Le entrega cada documento a su adquiriente a través de rededoc y devuelve los ids
    de los que quedaron notificados.

    Solo se notifica lo que la DIAN ya validó —la representación gráfica lleva el
    CUFE y la fecha de validación, y rededoc rechaza lo que no esté aceptado— y a un
    cliente con correo (`correo_notificacion`). Un
    documento ya notificado se puede volver a notificar: es la forma de reenviarle
    la factura a un cliente que la perdió, o después de corregirle el correo.

    Como en `emitir`, el lote se valida entero antes de enviar el primero, pero el
    envío no es atómico: cada documento se marca apenas rededoc lo acepta, y si uno
    falla el error dice cuáles ya salieron.
    """
    # El import va acá: `documento_imprimir` arrastra los formatos, y los
    # formatos no tienen por qué cargarse para crear un emisor.
    from general.servicios import documento_imprimir

    if not documento_ids:
        raise ValidationError({'ids': 'Este campo es requerido.'})
    _parametro_habilitado()

    documentos = (
        GenDocumento.objects
        .select_related(
            'documento_tipo', 'resolucion', 'metodo_pago', 'plazo_pago',
            'cuenta_banco__cuenta_banco_tipo', 'contacto__identificacion', 'contacto__ciudad',
        )
        .prefetch_related('documentos_detalles_documento_rel__item')
        .in_bulk(documento_ids)
    )
    for documento_id in documento_ids:
        documento = documentos.get(documento_id)
        if documento is None:
            raise NotFound(f'El documento {documento_id} no existe.')
        if not (documento.estado_electronico and documento.cue and documento.electronico_id):
            raise ErrorFacturaElectronica(
                f'El documento {documento_id} todavía no ha sido validado por la DIAN.'
            )
        if not correo_notificacion(documento):
            raise ErrorFacturaElectronica(f'El cliente del documento {documento_id} no tiene correo.')

    cliente = cliente or Rededoc()
    notificados = []
    for documento_id in documento_ids:
        documento = documentos[documento_id]
        pdf, nombre = documento_imprimir.pdf_documento(documento)
        # Se manda el correo y no se deja el que rededoc tenga del adquiriente: si
        # el cliente lo corrigió después de emitir, un reenvío tiene que llegar al
        # nuevo.
        respuesta = cliente.notificar_documento(
            documento.electronico_id, pdf, nombre, correo_notificacion(documento),
        )
        if respuesta['error']:
            status = 400 if 400 <= respuesta['status'] < 500 else 502
            raise ErrorFacturaElectronica(
                {
                    'detail': (
                        'El servicio de facturación electrónica no pudo notificar el '
                        f'documento {documento.id}.'
                    ),
                    'documento': documento.id,
                    'notificados': notificados,
                    'error': respuesta['datos'],
                },
                status=status,
            )
        documento.estado_electronico_notificado = True
        documento.save(update_fields=['estado_electronico_notificado'])
        notificados.append(documento.id)
    return notificados
