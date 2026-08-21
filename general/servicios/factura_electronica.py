"""
Creación del emisor del cliente en el servicio de facturación electrónica (rededoc).

El flujo es front → back → rededoc. El front solo dispara la acción: el payload
lo arma el back leyendo `GenConfiguracion`, nunca lo que mande el navegador. Si
el NIT y la razón social vinieran del front, un cliente podría registrar un
emisor a nombre de otra empresa.

El emisor queda en `GenParametro`, que es de solo lectura para el tenant: es un
hecho verificado contra rededoc, no algo que el cliente afirme. Crear el emisor
no activa la facturación electrónica; `gen_factura_electronica_activa` se maneja
aparte.
"""

from general.models import GenConfiguracion, GenParametro
from general.servicios.rededoc import Rededoc

EXTENSIONES_CERTIFICADO = ('.p12', '.pfx')
TAMANO_MAXIMO_CERTIFICADO = 1024 * 1024  # 1 MB; un certificado real pesa unos pocos KB


class ErrorFacturaElectronica(Exception):
    """
    Falla esperable de la activación. La vista la traduce a una respuesta HTTP.

    `cuerpo` es lo que sale tal cual en la respuesta: un texto nuestro se envuelve
    en `detail`, y el cuerpo de error de rededoc pasa sin tocar, porque ya viene
    con esa misma forma. Envolverlo otra vez dejaba al front con el error anidado
    dentro del error, y con un `detail` externo que además podía mentir.
    """

    def __init__(self, cuerpo, status=400):
        super().__init__(cuerpo)
        self.cuerpo = {'detail': cuerpo} if isinstance(cuerpo, str) else (cuerpo or {})
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
    parametro.gen_factura_electronica_emisor = emisor_id
    parametro.save(update_fields=['gen_factura_electronica_emisor'])
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
    if not parametro.gen_factura_electronica_emisor:
        raise ErrorFacturaElectronica(
            'Primero hay que crear el emisor en el servicio de facturación electrónica.',
        )

    cliente = cliente or Rededoc()
    archivo.seek(0)
    respuesta = cliente.cargar_certificado(
        parametro.gen_factura_electronica_emisor, archivo, clave, nombre=nombre,
    )
    if respuesta['error']:
        status = 400 if 400 <= respuesta['status'] < 500 else 502
        raise ErrorFacturaElectronica(respuesta['datos'], status=status)
    return respuesta['datos'] or {}
