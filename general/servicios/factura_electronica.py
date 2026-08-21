"""
Activación del cliente en el servicio de facturación electrónica (rededoc).

El flujo es front → back → rededoc. El front solo dispara la acción: el payload
lo arma el back leyendo `GenConfiguracion`, nunca lo que mande el navegador. Si
el NIT y la razón social vinieran del front, un cliente podría registrar un
emisor a nombre de otra empresa.

Al terminar, el resultado queda en `GenParametro`, que es de solo lectura para
el tenant: la activación es un hecho verificado contra rededoc, no algo que el
cliente afirme.
"""

from general.models import GenConfiguracion, GenParametro
from general.servicios.rededoc import Rededoc


class ErrorFacturaElectronica(Exception):
    """Falla esperable de la activación. La vista la traduce a una respuesta HTTP."""

    def __init__(self, mensaje, detalle=None, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle
        self.status = status


def _mensaje_y_detalle(datos, generico):
    """
    Saca el mensaje de la respuesta de error de rededoc.

    Rededoc ya responde con la misma forma que nosotros (`{'detail': ...,
    'errores': {...}}`), así que envolverla tal cual deja al front con el error
    anidado dentro del error, y con un `detail` externo que además puede mentir:
    "no se pudo contactar" cuando el servicio sí contestó y explicó por qué. Si
    trae `detail`, ese texto es el mensaje y solo `errores` baja como detalle.
    """
    datos = datos if isinstance(datos, dict) else {}
    detail = datos.get('detail')
    if isinstance(detail, str) and detail.strip():
        return detail, (datos.get('errores') or None)
    return generico, (datos or None)


def activar(cliente: Rededoc = None) -> GenParametro:
    """
    Crea el emisor del tenant en rededoc y deja el resultado en `GenParametro`.

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

    payload = {
        'razon_social': configuracion.gen_empresa_razon_social,
        'nombre_comercial': configuracion.gen_empresa_nombre_corto,
        'tipo_identificacion': configuracion.gen_empresa_identificacion_id,
        'numero_identificacion': configuracion.gen_empresa_numero_identificacion,
        'digito_verificacion': configuracion.gen_empresa_digito_verificacion or '',
        'tipo_organizacion': configuracion.gen_empresa_tipo_persona_id,
        'pais': estado.pais_id,
        'departamento': ciudad.estado_id,
        'municipio': ciudad.id,
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
        mensaje, detalle = _mensaje_y_detalle(
            respuesta['datos'],
            'El servicio de facturación electrónica rechazó los datos de la empresa.'
            if status == 400 else
            'No se pudo contactar el servicio de facturación electrónica.',
        )
        raise ErrorFacturaElectronica(mensaje, detalle=detalle, status=status)
    emisor_id = (respuesta['datos'] or {}).get('id')

    parametro, _ = GenParametro.objects.get_or_create(id=1)
    parametro.gen_factura_electronica_activa = True
    parametro.gen_factura_electronica_emisor = emisor_id
    parametro.save(update_fields=[
        'gen_factura_electronica_activa',
        'gen_factura_electronica_emisor',
    ])
    return parametro
