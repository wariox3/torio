"""
Facturación electrónica con rededoc: creación del emisor, carga del certificado y
emisión de documentos.

El flujo es front → back → rededoc. El front solo dispara la acción: el payload
lo arma el back leyendo `GenConfiguracion`, nunca lo que mande el navegador. Si
el NIT y la razón social vinieran del front, un cliente podría registrar un
emisor a nombre de otra empresa.

El emisor queda en `GenParametro`, que es de solo lectura para el tenant: es un
hecho verificado contra rededoc, no algo que el cliente afirme. Crear el emisor
no habilita la emisión: hasta que se termine el asistente
(`gen_asistente_electronico_venta`) no se emite.
"""

import calendar
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from general.models import (
    GenConfiguracion,
    GenDocumento,
    GenDocumentoElectronicoError,
    GenIdentificacion,
    GenParametro,
    GenResolucion,
)
from general.servicios.documento import (
    DOCUMENTO_CLASE_DOCUMENTO_SOPORTE,
    DOCUMENTO_CLASE_FACTURA_VENTA,
    DOCUMENTO_CLASE_NOTA_CREDITO_VENTA,
    DOCUMENTO_CLASE_NOTA_DEBITO_VENTA,
)
from general.servicios.rededoc import Rededoc
from utilidades.excepciones import con_detail
from utilidades.zinc import Zinc

EXTENSIONES_CERTIFICADO = ('.p12', '.pfx')
TAMANO_MAXIMO_CERTIFICADO = 1024 * 1024  # 1 MB; un certificado real pesa unos pocos KB
MODULOS_SOFTWARE = ('facturacion', 'nomina')
# Tipos de software de rededoc (`Software.Tipo`): la DIAN habilita cada operación
# con su propio SoftwareID. No confundir con `MODULOS_SOFTWARE`, el filtro de la
# consulta: el de documento equivalente es del módulo `facturacion`.
TIPOS_SOFTWARE = ('facturacion', 'nomina', 'documento_equivalente')


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


# Módulo del asistente → campo de `GenParametro` que lo marca pendiente.
CAMPO_ASISTENTE_POR_MODULO = {
    'venta': 'gen_asistente_electronico_venta',
    'nomina': 'gen_asistente_electronico_nomina',
}


def asistente_terminar(modulo: str) -> str:
    """
    Apaga el asistente de facturación electrónica de `modulo` y devuelve el
    campo que apagó. Terminar el de venta es lo que deja emitir. Repetirlo deja
    todo igual.
    """
    campo = CAMPO_ASISTENTE_POR_MODULO[modulo]
    parametro, _ = GenParametro.objects.get_or_create(id=1)
    if getattr(parametro, campo):
        setattr(parametro, campo, False)
        parametro.save(update_fields=[campo])
    return campo


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


def software_actualizar(software_id: int, datos: dict, cliente: Rededoc = None) -> dict:
    """
    Actualiza en rededoc un software DIAN del emisor de `gen_rededoc_emisor`.

    El id viene del front, y todos los emisores cuelgan de la misma API key de
    torio: rededoc aceptaría el PATCH sobre el software de otra empresa. Por eso
    antes se consulta y se exige que su `emisor` sea el del tenant. Que no exista
    y que sea ajeno responden lo mismo, para no revelar qué softwares hay.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_un_software(software_id)
    if respuesta['error'] and respuesta['status'] != 404:
        raise _error_rededoc(respuesta)
    emisor_software = None if respuesta['error'] else (respuesta['datos'] or {}).get('emisor')
    if emisor_software is None or str(emisor_software) != str(emisor_id):
        raise ErrorFacturaElectronica('El software no existe.', status=404)

    respuesta = cliente.actualizar_software(software_id, datos)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def resoluciones_validar(venta: bool = None, compra: bool = None, cliente: Rededoc = None) -> dict:
    """
    Valida contra la DIAN, a través de rededoc, las resoluciones vigentes del
    tenant, y marca como inactivas las que ya vencieron.

    Con `venta` o `compra` el proceso entero se limita a las resoluciones de un
    módulo: cada uno filtra por su campo, en `True` o en `False`. Sin ninguno,
    todas.

    A rededoc se mandan las que no han vencido, cada una con su `id` de torio.
    Rededoc responde una entrada por resolución, en el mismo orden y sin id, así
    que cada resultado se empareja con su resolución por la posición.
    `estado_validado` queda en lo que rededoc responda en `validado`: que el
    emisor tiene esa resolución en la DIAN.

    Devuelve `inactivadas`, `validadas` y `resoluciones`: la respuesta de
    rededoc —que además dice si hay `inconsistencia` en el rango o la
    vigencia— con el `id` de torio de cada una.

    Que el emisor no tenga un software aceptado por la DIAN, o que la DIAN no
    devuelva rangos, lo dice rededoc con un 400 y su mensaje es el que sube al
    front; en ese caso no se cambia nada.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    hoy = timezone.localdate()

    # Vencida es la que ya pasó su último día de vigencia: con `fecha_hasta` hoy
    # todavía numera. Sin número no hay qué buscar en la DIAN.
    resoluciones = GenResolucion.objects.all()
    if venta is not None:
        resoluciones = resoluciones.filter(venta=venta)
    if compra is not None:
        resoluciones = resoluciones.filter(compra=compra)
    vigentes = list(
        resoluciones.filter(fecha_hasta__gte=hoy)
        .exclude(numero__isnull=True).exclude(numero='')
    )
    resultados = []
    if vigentes:
        respuesta = cliente.validar_resoluciones(emisor_id, [
            {
                'id': resolucion.id,
                'numero_resolucion': resolucion.numero,
                'prefijo': resolucion.prefijo or '',
                'rango_desde': resolucion.consecutivo_desde,
                'rango_hasta': resolucion.consecutivo_hasta,
                'vigente_desde': resolucion.fecha_desde.isoformat(),
                'vigente_hasta': resolucion.fecha_hasta.isoformat(),
            }
            for resolucion in vigentes
        ])
        if respuesta['error']:
            raise _error_rededoc(respuesta)
        datos = respuesta['datos'] or []
        # Emparejar por posición solo sirve si llegó una entrada por cada
        # resolución enviada; con otra cantidad se marcaría la que no es.
        if len(datos) != len(vigentes):
            raise ErrorFacturaElectronica(
                'El servicio de facturación electrónica respondió una cantidad de '
                'resoluciones distinta a la enviada.',
                status=502,
            )
        resultados = [
            {**resultado, 'id': resolucion.id}
            for resolucion, resultado in zip(vigentes, datos)
        ]

    validados = [r['id'] for r in resultados if r.get('validado')]
    no_validados = [r['id'] for r in resultados if not r.get('validado')]

    inactivadas = resoluciones.filter(
        fecha_hasta__lt=hoy, estado_inactivo=False,
    ).update(estado_inactivo=True)
    GenResolucion.objects.filter(id__in=validados).update(estado_validado=True)
    GenResolucion.objects.filter(id__in=no_validados).update(estado_validado=False)
    return {'inactivadas': inactivadas, 'validadas': len(validados), 'resoluciones': resultados}


# El `tipo_factura` de rededoc (id de su catálogo) que es de compra: el documento
# soporte, código DIAN 05. Los demás tipos que se numeran con resolución —factura
# de venta, P.O.S.— son de venta.
REDEDOC_TIPO_FACTURA_DOCUMENTO_SOPORTE = 7


# Ambiente de la DIAN de las resoluciones que se listan: producción. Fijo, y no
# `REDEDOC_AMBIENTE`: las de habilitación son las del Set de Pruebas, que no sirven
# para numerar documentos reales.
AMBIENTE_RESOLUCIONES = 1
# Módulos de rededoc por los que se puede filtrar. `nomina` existe allá, pero acá
# las resoluciones son solo de venta o de compra.
MODULOS_RESOLUCIONES = ('facturacion', 'compras')


def resoluciones_consultar(modulo: str = None, pagina: int = None, cliente: Rededoc = None) -> dict:
    """
    Le pide a rededoc que traiga de la DIAN las resoluciones del emisor de
    `gen_rededoc_emisor` y devuelve una página de las que le quedan registradas.

    No crea nada en torio: la que se necesite se trae con `resolucion_importar`.
    Rededoc responde como su listado, y se le piden solo las de producción
    (`AMBIENTE_RESOLUCIONES`) y, si viene, las del `modulo`. Sin ninguna se
    responde la lista vacía, no un error.

    Si rededoc no puede importar —el emisor no tiene software, la DIAN no devuelve
    rangos o no responde— sube su error.

    Rededoc pagina, y sus `next` y `previous` son direcciones suyas, que al front
    no le sirven: se devuelven `count` y `results`, y la página se pide con
    `pagina`.

    Cada resolución lleva `importada`: si la empresa ya tiene una con ese número y
    prefijo, que es lo mismo que mira `resolucion_importar` para rechazarla.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()

    respuesta = cliente.importar_resoluciones(
        emisor_id, AMBIENTE_RESOLUCIONES, modulo, pagina,
    )
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    datos = respuesta['datos'] or {}
    resultados = datos.get('results') or []
    # Sin prefijo se guarda `None` o vacío según por dónde haya entrado: los dos
    # son la misma resolución.
    existentes = {
        (numero, prefijo or '')
        for numero, prefijo in GenResolucion.objects
        .filter(numero__in=[r.get('numero_resolucion') for r in resultados])
        .values_list('numero', 'prefijo')
    }
    return {
        'count': datos.get('count', 0),
        'results': [
            {**r, 'importada': (r.get('numero_resolucion'), r.get('prefijo') or '') in existentes}
            for r in resultados
        ],
    }


def resolucion_importar(resolucion_id: int, cliente: Rededoc = None) -> GenResolucion:
    """
    Crea en torio la resolución que rededoc tiene con ese id.

    Rededoc ya la trajo de la DIAN, así que entra con `estado_validado` en
    verdadero. La clave técnica no se copia: rededoc no la devuelve, y es él
    quien calcula el CUFE.

    El id viene del front, y todos los emisores cuelgan de la misma API key de
    torio: rededoc respondería la resolución de otra empresa. Por eso se exige
    que su `emisor` sea el del tenant. Que no exista y que sea ajena responden lo
    mismo, para no revelar qué resoluciones hay.

    Si la empresa ya tiene una con el mismo número y prefijo no se crea otra ni
    se toca la que está: responde 400.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()

    # Con el emisor, rededoc solo encuentra la resolución si es de él: la de
    # otra empresa responde 404, igual que una que no existe.
    respuesta = cliente.consultar_resolucion(resolucion_id, emisor_id)
    if respuesta['error'] and respuesta['status'] != 404:
        raise _error_rededoc(respuesta)
    datos = None if respuesta['error'] else (respuesta['datos'] or {})
    if datos is None or str(datos.get('emisor')) != str(emisor_id):
        raise ErrorFacturaElectronica('La resolución no existe.', status=404)

    numero = datos.get('numero_resolucion')
    prefijo = datos.get('prefijo') or None
    existentes = GenResolucion.objects.filter(numero=numero)
    if prefijo is None:
        existentes = existentes.filter(Q(prefijo__isnull=True) | Q(prefijo=''))
    else:
        existentes = existentes.filter(prefijo=prefijo)
    if existentes.exists():
        raise ErrorFacturaElectronica(
            f'La resolución {numero} con prefijo {prefijo or "sin prefijo"} ya existe.'
        )

    compra = datos.get('tipo_factura') == REDEDOC_TIPO_FACTURA_DOCUMENTO_SOPORTE
    return GenResolucion.objects.create(
        numero=numero,
        prefijo=prefijo,
        consecutivo_desde=datos.get('rango_desde'),
        consecutivo_hasta=datos.get('rango_hasta'),
        fecha_desde=datos.get('vigente_desde'),
        fecha_hasta=datos.get('vigente_hasta'),
        venta=not compra,
        compra=compra,
        estado_validado=True,
    )


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
# Lo mismo para las retenciones, que solo viajan en el documento soporte. Acá no
# hay valor por defecto: una retención que saliera con el tributo equivocado se
# le informaría a la DIAN como otra, así que la que no esté acá corta la emisión.
RETENCIONES = {'RTF': '06', 'RTI': '05'}
# Las notas no se numeran contra una resolución de la DIAN, así que no tienen de
# dónde heredar el prefijo: llevan uno fijo por clase.
PREFIJOS_NOTA = {
    DOCUMENTO_CLASE_NOTA_CREDITO_VENTA: 'NC',
    DOCUMENTO_CLASE_NOTA_DEBITO_VENTA: 'ND',
}
# El concepto «Anulación de factura electrónica» de la nota crédito. Es el único
# que exige la factura referenciada: rededoc deja ir las demás notas crédito y
# débito «sin referencia a facturas» (CustomizationID 22 y 32), pero anular sin
# decir qué factura no tiene sentido. El «2» de la nota débito es otra cosa
# (gastos por cobrar), por eso se mira también la clase.
CONCEPTO_ANULACION = '2'

DOS_DECIMALES = Decimal('0.01')


class _ErroresDocumento(Exception):
    """Todo lo que le falta a un documento para poder armarse, no solo lo primero."""

    def __init__(self, mensajes):
        super().__init__(mensajes)
        self.mensajes = mensajes


def emitir(documento_ids, cliente: Rededoc = None) -> dict:
    """
    Crea en rededoc cada documento y devuelve `emitidos` y `con_error`, los ids de
    los que quedaron creados y de los que no.

    Cada documento va por su cuenta: el que no pasa las validaciones, o el que
    rededoc rechaza, no detiene a los demás. Sus motivos quedan en
    `GenDocumentoElectronicoError` y el documento con `estado_electronico_error`,
    que es donde el front los lee; la respuesta solo dice a cuáles les pasó. Cada
    intento reemplaza los errores del anterior, y uno que sale bien los borra.

    Uno que ya estaba enviado se salta sin tocarlo: no es un error suyo, y
    marcarlo dejaría con aviso un documento que está bien.

    Lo que sí corta el lote es lo que no es de ningún documento: que la empresa no
    pueda emitir, un id que no existe, o que rededoc no responda —ahí no se marca
    nada, porque el documento no tiene nada que corregir, y el error dice cuáles
    alcanzaron a salir—.
    """
    if not documento_ids:
        raise ValidationError({'ids': 'Este campo es requerido.'})
    parametro = _parametro_habilitado()

    documentos = GenDocumento.objects.select_related(
        'documento_tipo', 'resolucion', 'plazo_pago', 'metodo_pago',
        'contacto__identificacion', 'contacto__ciudad__estado__pais',
        'documento_referencia', 'documento_concepto_correccion',
    ).in_bulk(documento_ids)
    for documento_id in documento_ids:
        if documento_id not in documentos:
            raise NotFound(f'El documento {documento_id} no existe.')

    cliente = cliente or Rededoc()
    emitidos, con_error = [], []
    # Un id repetido en el lote se procesa una sola vez.
    for documento_id in dict.fromkeys(documento_ids):
        documento = documentos[documento_id]
        if documento.estado_electronico_enviado:
            continue

        try:
            payload = _validar_y_armar(documento, parametro)
        except _ErroresDocumento as e:
            _registrar_errores(documento, GenDocumentoElectronicoError.Fase.VALIDACION, e.mensajes)
            con_error.append(documento.id)
            continue

        respuesta = cliente.crear_documento(payload)
        if respuesta['error'] and not 400 <= respuesta['status'] < 500:
            raise ErrorFacturaElectronica(
                {
                    'detail': 'El servicio de facturación electrónica no respondió.',
                    'emitidos': emitidos,
                    'con_error': con_error,
                    'error': respuesta['datos'],
                },
                status=502,
            )
        if respuesta['error']:
            _registrar_errores(
                documento, GenDocumentoElectronicoError.Fase.EMISION,
                _mensajes_rededoc(respuesta['datos'])
                or ['El servicio de facturación electrónica rechazó el documento.'],
            )
            con_error.append(documento.id)
            continue

        with transaction.atomic():
            documento.documentos_electronicos_errores_documento_rel.all().delete()
            documento.electronico_id = (respuesta['datos'] or {}).get('id')
            documento.estado_electronico_enviado = True
            documento.estado_electronico_error = False
            documento.save(update_fields=[
                'electronico_id', 'estado_electronico_enviado', 'estado_electronico_error',
            ])
        emitidos.append(documento.id)
    return {'emitidos': emitidos, 'con_error': con_error}


def _validar_y_armar(documento, parametro):
    """El payload del documento, o `_ErroresDocumento` con todo lo que le falta."""
    errores = []
    if not documento.estado_aprobado:
        errores.append(f'El documento {documento.id} debe estar aprobado.')
    if documento.documento_tipo.documento_clase_id not in ARMADORES:
        errores.append(
            f'El documento {documento.id} es de un tipo que todavía no se emite electrónicamente.'
        )
        raise _ErroresDocumento(errores)
    try:
        payload = _armar(documento, parametro)
    except _ErroresDocumento as e:
        raise _ErroresDocumento(errores + e.mensajes)
    if errores:
        raise _ErroresDocumento(errores)
    return payload


def _registrar_errores(documento, fase, mensajes):
    """Reemplaza los errores del documento por los de este intento y lo marca."""
    with transaction.atomic():
        documento.documentos_electronicos_errores_documento_rel.all().delete()
        GenDocumentoElectronicoError.objects.bulk_create([
            GenDocumentoElectronicoError(documento=documento, fase=fase, mensaje=mensaje)
            for mensaje in mensajes
        ])
        documento.estado_electronico_error = True
        documento.save(update_fields=['estado_electronico_error'])


# Claves con las que un error viene suelto, sin ser de ningún campo.
_CLAVES_SIN_CAMPO = ('detail', 'mensaje', 'non_field_errors')


def _mensajes_rededoc(datos, ruta=''):
    """
    El cuerpo de error de rededoc, aplanado en un mensaje por renglón.

    Rededoc responde los errores con la forma del payload —`{'adquiriente':
    {'correo': [...]}, 'detalles': [{}, {'impuestos': [...]}]}`—; cada mensaje sale
    con el camino hasta su campo por delante (`detalles[1].impuestos[0].tributo: …`),
    que es lo que le dice al usuario qué corregir.
    """
    if isinstance(datos, dict):
        mensajes = []
        for clave, valor in datos.items():
            if clave in _CLAVES_SIN_CAMPO:
                hija = ruta
            else:
                hija = f'{ruta}.{clave}' if ruta else str(clave)
            mensajes.extend(_mensajes_rededoc(valor, hija))
        return mensajes
    if isinstance(datos, (list, tuple)):
        mensajes = []
        for indice, valor in enumerate(datos):
            anidado = isinstance(valor, (dict, list, tuple))
            mensajes.extend(_mensajes_rededoc(valor, f'{ruta}[{indice}]' if anidado else ruta))
        return mensajes
    if datos in (None, ''):
        return []
    return [f'{ruta}: {datos}' if ruta else str(datos)]


def _parametro_habilitado():
    """El `GenParametro` de una empresa que puede usar la facturación electrónica."""
    parametro = GenParametro.objects.filter(id=1).first()
    if parametro is None or parametro.gen_asistente_electronico_venta:
        raise ErrorFacturaElectronica('La empresa no ha terminado el asistente de facturación electrónica.')
    if not parametro.gen_rededoc_emisor:
        raise ErrorFacturaElectronica('La empresa no tiene emisor en el servicio de facturación electrónica.')
    return parametro


def _armar(documento, parametro):
    return ARMADORES[documento.documento_tipo.documento_clase_id](documento, parametro)


def _armar_factura_venta(documento, parametro):
    return _armar_con_resolucion(documento, parametro, contacto='cliente', con_retenciones=False)


def _armar_documento_soporte(documento, parametro):
    """
    El documento soporte viaja con la forma de la factura, leída desde la compra:
    lo expide la empresa, que es quien compra, así que en `adquiriente` va el
    vendedor —el no obligado a facturar—; rededoc los cruza al armar el XML.

    Se numera contra su propia resolución, igual que la factura, y es el único
    que lleva las retenciones: rededoc las reconoce por el tributo y las deja
    fuera del total a pagar.
    """
    return _armar_con_resolucion(documento, parametro, contacto='proveedor', con_retenciones=True)


def _armar_con_resolucion(documento, parametro, contacto, con_retenciones):
    """
    El payload de un documento que se numera contra una resolución. `contacto` es
    cómo se le dice al tercero en los mensajes de error.

    Revisa todo antes de fallar: quien corrige el documento tiene que ver de una
    vez lo que le falta, no un error distinto en cada intento.
    """
    errores = []
    if documento.documento_tipo.codigo is None:
        errores.append(
            f'El tipo de documento {documento.documento_tipo.nombre} no tiene código de '
            'facturación electrónica.'
        )
    if documento.numero is None:
        errores.append(f'El documento {documento.id} no tiene número.')
    if documento.fecha is None:
        errores.append(f'El documento {documento.id} no tiene fecha.')

    resolucion = documento.resolucion
    if resolucion is None:
        errores.append(f'El documento {documento.id} no tiene resolución.')
    else:
        if documento.numero is not None and not (
            resolucion.consecutivo_desde <= documento.numero <= resolucion.consecutivo_hasta
        ):
            errores.append(
                f'El número {documento.numero} del documento {documento.id} está fuera del rango '
                f'de la resolución, que va desde {resolucion.consecutivo_desde} hasta '
                f'{resolucion.consecutivo_hasta}.'
            )
        if documento.fecha is not None and not (
            resolucion.fecha_desde <= documento.fecha <= resolucion.fecha_hasta
        ):
            errores.append(
                f'La fecha {documento.fecha} del documento {documento.id} está fuera de la vigencia '
                f'de la resolución, que va desde {resolucion.fecha_desde} hasta {resolucion.fecha_hasta}.'
            )

    credito = bool(documento.plazo_pago and documento.plazo_pago.dias > 0)
    if credito and documento.fecha_vence is None:
        errores.append(
            f'El documento {documento.id} es a crédito y no tiene fecha de vencimiento.'
        )

    adquiriente = _o_error(errores, _adquiriente, documento, contacto)
    detalles = _o_error(errores, _detalles, documento, con_retenciones)
    if errores:
        raise _ErroresDocumento(errores)

    return {
        'emisor': parametro.gen_rededoc_emisor,
        'ambiente': settings.REDEDOC_AMBIENTE,
        # El id del documento en torio, para ubicarlo en rededoc sin su UUID.
        'referencia_externa': str(documento.id),
        'documento_tipo': documento.documento_tipo.codigo,
        'prefijo': resolucion.prefijo or '',
        'numero_resolucion': resolucion.numero,
        'consecutivo': documento.numero,
        'fecha_emision': documento.fecha.isoformat(),
        'fecha_vencimiento': documento.fecha_vence.isoformat() if credito else None,
        'forma_pago': FORMA_PAGO_CREDITO if credito else FORMA_PAGO_CONTADO,
        'medio_pago': getattr(documento.metodo_pago, 'codigo', None) or MEDIO_PAGO_NO_DEFINIDO,
        'moneda': MONEDA,
        'adquiriente': adquiriente,
        'detalles': detalles,
    }


def _armar_nota(documento, parametro):
    """
    La nota crédito o débito de venta: corrige una factura y viaja con el
    concepto que dice por qué.

    La factura corregida (`documento_referencia`, con el id que tiene en
    rededoc) es opcional: sin ella la nota sale como «sin referencia a
    facturas». La exige solo la anulación (`CONCEPTO_ANULACION` en la nota
    crédito), igual que rededoc. Si la factura no tiene `electronico_id` (se
    emitió por fuera de torio, p. ej. desde itrio) la nota también sale sin
    referencia; solo la anulación exige que esté enviada.

    No se numera contra una resolución —va con su prefijo de `PREFIJOS_NOTA` y
    la resolución vacía— ni lleva vencimiento, que rededoc rechaza en una nota.
    Las retenciones tampoco viajan, igual que en la factura.
    """
    clase_id = documento.documento_tipo.documento_clase_id
    errores = []
    if documento.documento_tipo.codigo is None:
        errores.append(
            f'El tipo de documento {documento.documento_tipo.nombre} no tiene código de '
            'facturación electrónica.'
        )
    if documento.numero is None:
        errores.append(f'El documento {documento.id} no tiene número.')
    if documento.fecha is None:
        errores.append(f'El documento {documento.id} no tiene fecha.')

    concepto = documento.documento_concepto_correccion
    if concepto is None:
        errores.append(f'El documento {documento.id} no tiene concepto de corrección.')

    referencia = documento.documento_referencia
    anulacion = (
        clase_id == DOCUMENTO_CLASE_NOTA_CREDITO_VENTA
        and concepto is not None and concepto.codigo == CONCEPTO_ANULACION
    )
    # Una factura sin `electronico_id` (p. ej. emitida desde itrio) no se puede
    # referenciar: la nota sale sin referencia, salvo la anulación, que la exige.
    referencia_electronica = referencia.electronico_id if referencia is not None else None
    if anulacion and referencia is None:
        errores.append(
            f'El documento {documento.id} es una anulación y no tiene la factura que anula.'
        )
    elif anulacion and not referencia_electronica:
        errores.append(
            f'El documento {referencia.numero or referencia.id} que anula la nota '
            f'{documento.id} no ha sido enviado electrónicamente.'
        )

    adquiriente = _o_error(errores, _adquiriente, documento, 'cliente')
    detalles = _o_error(errores, _detalles, documento, False)
    if errores:
        raise _ErroresDocumento(errores)

    credito = bool(documento.plazo_pago and documento.plazo_pago.dias > 0)
    return {
        'emisor': parametro.gen_rededoc_emisor,
        'ambiente': settings.REDEDOC_AMBIENTE,
        'referencia_externa': str(documento.id),
        'documento_tipo': documento.documento_tipo.codigo,
        'prefijo': PREFIJOS_NOTA[clase_id],
        'numero_resolucion': '',
        'consecutivo': documento.numero,
        'fecha_emision': documento.fecha.isoformat(),
        'fecha_vencimiento': None,
        'forma_pago': FORMA_PAGO_CREDITO if credito else FORMA_PAGO_CONTADO,
        'medio_pago': getattr(documento.metodo_pago, 'codigo', None) or MEDIO_PAGO_NO_DEFINIDO,
        'moneda': MONEDA,
        'documento_referencia': str(referencia_electronica) if referencia_electronica else None,
        'concepto_correccion': concepto.codigo,
        'adquiriente': adquiriente,
        'detalles': detalles,
    }


def _o_error(errores, armar, *args):
    """Lo que devuelva `armar`, o `None` dejando su error en la lista."""
    try:
        return armar(*args)
    except ErrorFacturaElectronica as e:
        errores.append(e.cuerpo['detail'])
        return None


def _adquiriente(documento, rol='cliente'):
    contacto = documento.contacto
    if contacto is None:
        raise ErrorFacturaElectronica(f'El documento {documento.id} no tiene {rol}.')

    ciudad = contacto.ciudad
    codigo_postal = contacto.codigo_postal or ciudad.codigo_postal
    if not codigo_postal:
        raise ErrorFacturaElectronica(
            f'El {rol} {contacto.nombre_corto} no tiene código postal, ni su ciudad uno por defecto.'
        )

    return {
        # Va el código DIAN (cédula = 13), que en rededoc es también su id; el
        # id del catálogo propio no coincide.
        'tipo_identificacion': int(contacto.identificacion.codigo),
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


def _detalles(documento, con_retenciones=False):
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
            'impuestos': _impuestos(linea, con_retenciones),
        })
    if not detalles:
        raise ErrorFacturaElectronica(f'El documento {documento.id} no tiene detalles para emitir.')
    return detalles


def _impuestos(linea, con_retenciones=False):
    # Las retenciones (operación negativa) solo van si el documento las admite:
    # en la factura rededoc las rechaza, porque no las separa del total a pagar.
    impuestos = []
    for impuesto in linea.documentos_impuestos_documento_detalle_rel.all():
        retencion = impuesto.impuesto.operacion < 0
        if retencion and not con_retenciones:
            continue
        impuestos.append({
            'tributo': _tributo(impuesto.impuesto, retencion),
            'base_gravable': _decimal(impuesto.base),
            'tarifa': _decimal(impuesto.porcentaje),
            'valor': _decimal(impuesto.total),
        })
    return impuestos


def _tributo(impuesto, retencion):
    tipo = getattr(impuesto.impuesto_tipo, 'codigo', None)
    if not retencion:
        return TRIBUTOS.get(tipo, TRIBUTO_POR_DEFECTO)
    if tipo not in RETENCIONES:
        raise ErrorFacturaElectronica(
            f'La retención {impuesto.nombre} no es de fuente ni de IVA, que son las que se '
            'pueden emitir electrónicamente.'
        )
    return RETENCIONES[tipo]


def _decimal(valor):
    return str((valor or Decimal('0')).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP))


ARMADORES = {
    DOCUMENTO_CLASE_FACTURA_VENTA: _armar_factura_venta,
    DOCUMENTO_CLASE_NOTA_CREDITO_VENTA: _armar_nota,
    DOCUMENTO_CLASE_NOTA_DEBITO_VENTA: _armar_nota,
    DOCUMENTO_CLASE_DOCUMENTO_SOPORTE: _armar_documento_soporte,
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

    - `validacion`: la DIAN aceptó el documento; guarda su CUFE y la fecha, y, si
      es de venta, programa su notificación al adquiriente (`general.tasks`). Un
      documento soporte o una nómina solo quedan validados. Si el documento ya
      estaba validado no se reescribe: responde 409, porque un CUFE no cambia, y
      uno distinto para el mismo documento es un error que hay que ver.
    - `notificacion`: el documento se le entregó al adquiriente. Repetirla deja el
      documento igual.
    """
    documento = (
        GenDocumento.objects.select_related('documento_tipo')
        .filter(electronico_id=documento_id).first()
    )
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
        #
        # Solo los de venta: son los que tienen un cliente esperando el documento.
        # En el documento soporte el adquiriente es la propia empresa, y la nómina
        # no se le entrega a nadie por este camino.
        if documento.documento_tipo.venta:
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


def electronico_log(documento_id, zinc: Zinc = None) -> list:
    """
    El registro de los correos con que se le entregó el documento a su
    adquiriente, tal como lo tiene zinc, que es la pasarela que los envía.

    Zinc lo busca por el id del documento en rededoc (`electronico_id`), bajo la
    aplicación `nobelio`. Solo tiene sentido para un documento ya notificado:
    antes de eso no se ha enviado ningún correo.
    """
    documento = GenDocumento.objects.filter(id=documento_id).first()
    if documento is None:
        raise NotFound(f'El documento {documento_id} no existe.')
    if not documento.estado_electronico_notificado:
        raise ErrorFacturaElectronica(f'El documento {documento_id} nunca ha sido notificado.')
    if not documento.electronico_id:
        raise ErrorFacturaElectronica(
            f'El documento {documento_id} está marcado como notificado pero no tiene id electrónico.'
        )

    zinc = zinc or Zinc()
    respuesta = zinc.log_envio(str(documento.electronico_id))
    if respuesta['error']:
        raise ErrorFacturaElectronica('El servicio de correo no respondió el registro de envíos.', status=502)
    return (respuesta['datos'] or {}).get('log', [])


def electronico_xml(documento_id, cliente: Rededoc = None) -> tuple:
    """
    El XML firmado del documento, tal como lo tiene rededoc, y el nombre con que
    se descarga.

    Rededoc lo busca por su propio id del documento (`electronico_id`), que solo
    existe después de emitir. Que el XML todavía no esté firmado lo responde
    rededoc, y su error sube tal cual.
    """
    documento = GenDocumento.objects.select_related('resolucion').filter(id=documento_id).first()
    if documento is None:
        raise NotFound(f'El documento {documento_id} no existe.')
    if not documento.electronico_id:
        raise ErrorFacturaElectronica(
            f'El documento {documento_id} no ha sido enviado electrónicamente.'
        )

    cliente = cliente or Rededoc()
    respuesta = cliente.descargar_xml(documento.electronico_id)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    prefijo = (documento.resolucion.prefijo if documento.resolucion_id else None) or ''
    return respuesta['datos'], f'{prefijo}{documento.numero}.xml'


# ------------------------------------------------------------ recepción ----

RECEPCION_DOCUMENTO_TIPOS = ('factura_venta', 'nota_credito', 'nota_debito')
RECEPCION_ORDENES = ('fecha_emision', 'numero', 'total_a_pagar', 'creado_en')
RECEPCION_VERIFICACION_ESTADOS = ('pendiente', 'valido', 'invalido', 'no_verificable', 'error')
RECEPCION_RADIAN_ESTADOS = ('sin_eventos', 'acuse', 'recibo', 'aceptada', 'reclamada')
RECEPCION_PAGINA = 25
RECEPCION_PAGINA_MAXIMA = 100


RECEPCION_CORREO_ESTADOS = (
    'pendiente', 'procesado', 'sin_documentos', 'error', 'empresa_desconocida', 'confirmacion_reenvio',
)
RECEPCION_CORREO_ORIGENES = ('correo', 'carga')
RECEPCION_CORREO_ORDENES = ('recibido_en', 'estado')
# Del correo de rededoc no salen: `raw_key` es la clave del MIME en su R2, y
# `usuario` el de rededoc que subió la carga, que con la llave de torio es
# siempre la cuenta de servicio de torio.
RECEPCION_CORREO_OCULTOS = ('raw_key', 'usuario')

RECEPCION_EVENTO_ESTADOS = ('pendiente', 'registrado', 'rechazado', 'error')
# 030 acuse, 031 reclamo, 032 recibo del bien o servicio, 033 aceptación.
RECEPCION_EVENTO_CODIGOS = ('030', '031', '032', '033')
RECEPCION_EVENTO_CON_PERSONA = ('030', '032')
RECEPCION_EVENTO_ORDENES = ('creado_en', 'numero')
# `usuario` es el de rededoc que pidió el evento: con la llave de torio, siempre
# la cuenta de servicio de torio.
RECEPCION_EVENTO_OCULTOS = ('usuario',)

RECEPCION_ADJUNTO_ROLES = ('xml', 'xml_documento', 'pdf', 'otro')
RECEPCION_ADJUNTO_PAGINA = 10  # fijo en rededoc: no acepta page_size


def _consulta_recepcion(filtros: dict, hoy) -> tuple:
    """
    Lo que comparten las bandejas de recepción: devuelve los filtros completos y
    los parámetros para rededoc.

    El `emisor` lo pone el back y nunca el front: la llave de torio alcanza a
    todos los emisores, y sin `emisor` rededoc responde los de todas las empresas.
    Sin `desde` ni `hasta` se consulta el mes de `hoy`, para no traer todo el
    histórico; con uno solo, el rango queda abierto del otro lado.
    """
    emisor_id = _emisor_id()
    hoy = hoy or timezone.localdate()
    filtros = dict(filtros)
    if not filtros.get('desde') and not filtros.get('hasta'):
        filtros['desde'] = hoy.replace(day=1)
        filtros['hasta'] = hoy.replace(day=calendar.monthrange(hoy.year, hoy.month)[1])
    filtros.setdefault('page', 1)
    filtros.setdefault('page_size', RECEPCION_PAGINA)

    parametros = {
        clave: valor.isoformat() if clave in ('desde', 'hasta') else valor
        for clave, valor in filtros.items()
        if valor not in (None, '')
    }
    parametros['emisor'] = emisor_id
    return filtros, parametros


def _bandeja(filtros: dict, datos: dict, resultados: list) -> dict:
    """
    La respuesta de una bandeja. `next` y `previous` de rededoc no salen: son URL
    de su API, con el emisor puesto. El front pagina con `page` y `count`.
    """
    return {
        'count': datos.get('count', 0),
        'page': filtros['page'],
        'page_size': filtros['page_size'],
        'desde': filtros.get('desde'),
        'hasta': filtros.get('hasta'),
        'results': resultados,
    }


def recepcion_documento(filtros: dict, hoy=None, cliente: Rededoc = None) -> dict:
    """
    La bandeja de documentos recibidos de proveedores del emisor de
    `gen_rededoc_emisor`. El rango va sobre la fecha de emisión.
    """
    filtros, parametros = _consulta_recepcion(filtros, hoy)
    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_documentos_recibidos(parametros)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    datos = respuesta['datos'] or {}
    return _bandeja(filtros, datos, datos.get('results', []))


def recepcion_correo(filtros: dict, hoy=None, cliente: Rededoc = None) -> dict:
    """
    Los correos (y cargas manuales) que llegaron a la recepción del emisor de
    `gen_rededoc_emisor`. El rango va sobre la fecha en que se recibieron.

    Un correo puede traer documentos de varios receptores, y rededoc deja dentro
    los que alcanza la llave, que en torio son los de todas las empresas: acá se
    quedan solo los del emisor del tenant.
    """
    filtros, parametros = _consulta_recepcion(filtros, hoy)
    emisor_id = parametros['emisor']
    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_correos_recibidos(parametros)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    datos = respuesta['datos'] or {}
    correos = [
        {
            **{campo: valor for campo, valor in correo.items() if campo not in RECEPCION_CORREO_OCULTOS},
            'documentos': [
                documento for documento in correo.get('documentos') or []
                if str(documento.get('emisor')) == str(emisor_id)
            ],
        }
        for correo in datos.get('results', [])
    ]
    return _bandeja(filtros, datos, correos)


def recepcion_evento(filtros: dict, cliente: Rededoc = None) -> dict:
    """
    Los eventos RADIAN que el emisor de `gen_rededoc_emisor` registró sobre sus
    documentos recibidos. A diferencia de las otras bandejas no hay rango de
    fechas —rededoc no filtra los eventos por fecha—, así que `desde` y `hasta`
    salen en nulo. El `emisor` lo pone el back, igual que en las demás.
    """
    emisor_id = _emisor_id()
    filtros = dict(filtros)
    filtros.pop('emisor', None)
    filtros.setdefault('page', 1)
    filtros.setdefault('page_size', RECEPCION_PAGINA)
    parametros = {
        clave: str(valor) if clave == 'documento' else valor
        for clave, valor in filtros.items()
        if valor not in (None, '')
    }
    parametros['emisor'] = emisor_id

    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_eventos_recibidos(parametros)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    datos = respuesta['datos'] or {}
    eventos = [
        {campo: valor for campo, valor in evento.items() if campo not in RECEPCION_EVENTO_OCULTOS}
        for evento in datos.get('results', [])
    ]
    return _bandeja(filtros, datos, eventos)


def recepcion_adjunto(filtros: dict, cliente: Rededoc = None) -> dict:
    """
    Los archivos que llegaron a la recepción del emisor de `gen_rededoc_emisor`:
    los de un documento (`xml`, `xml_documento`, `pdf`) y los demás del correo
    (`otro`). Se acotan con `correo`, `documento`, `rol` y `search`.

    El `emisor` lo pone el back: con él rededoc solo responde los adjuntos de ese
    emisor, así que un correo o documento de otra empresa sale vacío. Rededoc
    pagina de a 10 sin dejar cambiar el tamaño: el front pagina con `page`.
    """
    emisor_id = _emisor_id()
    filtros = dict(filtros)
    filtros.pop('emisor', None)
    filtros.setdefault('page', 1)
    parametros = {
        clave: str(valor) if clave == 'documento' else valor
        for clave, valor in filtros.items()
        if valor not in (None, '')
    }
    parametros['emisor'] = emisor_id

    cliente = cliente or Rededoc()
    respuesta = cliente.consultar_adjuntos_recibidos(parametros)
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    datos = respuesta['datos'] or {}
    return {
        'count': datos.get('count', 0),
        'page': filtros['page'],
        'page_size': RECEPCION_ADJUNTO_PAGINA,
        'results': datos.get('results', []),
    }


def recepcion_documento_descartar(documento_id, cliente: Rededoc = None) -> dict:
    """
    Descarta un documento recibido del emisor de `gen_rededoc_emisor` y devuelve
    el documento como queda en rededoc.

    El `emisor` va en la consulta, así que uno de otra empresa responde 404 en
    rededoc, igual que uno que no existe; acá los dos son 404. Si no se puede
    descartar (ya descartado, recepción terminada o con eventos), el 400 de
    rededoc sube con su mensaje.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.descartar_documento_recibido(documento_id, emisor_id)
    if respuesta['error']:
        if respuesta['status'] == 404:
            raise ErrorFacturaElectronica('El documento no existe.', status=404)
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def recepcion_documento_restaurar(documento_id, cliente: Rededoc = None) -> dict:
    """
    Quita el descarte de un documento recibido del emisor de `gen_rededoc_emisor`
    y devuelve el documento como queda en rededoc. Uno de otra empresa o que no
    existe es 404; si no está descartado, el 400 de rededoc sube con su mensaje.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.restaurar_documento_recibido(documento_id, emisor_id)
    if respuesta['error']:
        if respuesta['status'] == 404:
            raise ErrorFacturaElectronica('El documento no existe.', status=404)
        raise _error_rededoc(respuesta)
    return respuesta['datos']


def recepcion_documento_evento(documento_id, datos: dict, cliente: Rededoc = None) -> dict:
    """
    Registra un evento RADIAN (030 a 033) sobre un documento recibido del emisor
    de `gen_rededoc_emisor` y devuelve el evento, que queda `pendiente`: rededoc
    lo envía a la DIAN en segundo plano y su estado se ve en el listado de eventos.

    `datos` es `{codigo, persona?, concepto_reclamo?}`, ya validado. Solo viaja
    lo que corresponde al código: la persona en 030 y 032, el concepto en 031.
    La persona trae `identificacion` como id de `GenIdentificacion`, y rededoc
    espera `tipo_identificacion` con el código DIAN: acá se convierte.

    Uno de otra empresa o que no existe es 404; si el evento no cabe, el 400 de
    rededoc sube con su mensaje.
    """
    emisor_id = _emisor_id()
    codigo = datos['codigo']
    cuerpo = {'codigo': codigo}
    if codigo in RECEPCION_EVENTO_CON_PERSONA:
        persona = dict(datos['persona'])
        identificacion = GenIdentificacion.objects.get(pk=persona.pop('identificacion'))
        cuerpo['persona'] = {'tipo_identificacion': int(identificacion.codigo), **persona}
    if codigo == '031':
        cuerpo['concepto_reclamo'] = datos['concepto_reclamo']

    cliente = cliente or Rededoc()
    respuesta = cliente.registrar_evento_recibido(documento_id, emisor_id, cuerpo)
    if respuesta['error']:
        if respuesta['status'] == 404:
            raise ErrorFacturaElectronica('El documento no existe.', status=404)
        raise _error_rededoc(respuesta)
    evento = respuesta['datos'] or {}
    return {campo: valor for campo, valor in evento.items() if campo not in RECEPCION_EVENTO_OCULTOS}


def recepcion_documento_eliminar(documento_id, cliente: Rededoc = None) -> None:
    """
    Elimina en rededoc un documento recibido del emisor de `gen_rededoc_emisor`,
    con sus archivos. Uno de otra empresa o que no existe es 404; si tiene
    eventos, el 400 de rededoc sube con su mensaje. Un 502 de rededoc (falló B2)
    deja todo como estaba: repetir termina el trabajo.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.eliminar_documento_recibido(documento_id, emisor_id)
    if respuesta['error']:
        if respuesta['status'] == 404:
            raise ErrorFacturaElectronica('El documento no existe.', status=404)
        raise _error_rededoc(respuesta)


def recepcion_adjunto_descargar(adjunto_id, cliente: Rededoc = None) -> tuple:
    """
    El contenido de un adjunto de la recepción del emisor de
    `gen_rededoc_emisor`: devuelve `(contenido, tipo_contenido, disposicion)`.

    El `emisor` va en la consulta, así que un adjunto de otra empresa responde
    404 en rededoc, igual que uno que no existe; acá los dos son 404.

    El nombre lo puso el proveedor: el `Content-Disposition` se toma tal cual lo
    arma rededoc (con el helper de Django, que escapa comillas y acentos), y si
    no fuera una descarga se fuerza a serlo, para que un HTML o un SVG de un
    tercero nunca se abra en el navegador con el origen de torio.
    """
    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    respuesta = cliente.descargar_adjunto_recibido(adjunto_id, emisor_id)
    if respuesta['error']:
        if respuesta['status'] == 404:
            raise ErrorFacturaElectronica('El adjunto no existe.', status=404)
        raise _error_rededoc(respuesta)
    cabeceras = respuesta.get('cabeceras') or {}
    tipo_contenido = cabeceras.get('Content-Type') or 'application/octet-stream'
    disposicion = cabeceras.get('Content-Disposition') or ''
    if not disposicion.lower().startswith('attachment'):
        disposicion = 'attachment'
    return respuesta['datos'], tipo_contenido, disposicion

# Tipo de contenido con el que sale cada extensión hacia rededoc.
EXTENSIONES_RECEPCION = {'.zip': 'application/zip', '.xml': 'application/xml'}
TAMANO_MAXIMO_RECEPCION = 10 * 1024 * 1024  # el mismo límite de rededoc


def recepcion_documento_cargar(archivo, cliente: Rededoc = None) -> tuple:
    """
    Manda a la recepción del emisor de `gen_rededoc_emisor` los documentos de un
    ZIP o XML, y devuelve `(datos, status)` de rededoc: 201 si creó alguno, 200 si
    todos ya estaban registrados. El cuerpo, `{creados, repetidos, rechazados}`,
    pasa tal cual.

    Extensión y tamaño se revisan acá para no reenviar 10 MB que rededoc va a
    rechazar; lo demás (archivo dañado, sin documentos, de otro receptor) lo
    valida rededoc y su mensaje es el que sube al front. El archivo no se guarda
    de este lado.
    """
    if archivo is None:
        raise ErrorFacturaElectronica('Falta el archivo.')
    nombre = archivo.name or ''
    extension = next((e for e in EXTENSIONES_RECEPCION if nombre.lower().endswith(e)), None)
    if extension is None:
        raise ErrorFacturaElectronica('El archivo debe ser un .zip o un .xml.')
    if archivo.size > TAMANO_MAXIMO_RECEPCION:
        raise ErrorFacturaElectronica(
            'El archivo supera el límite de {} MB.'.format(TAMANO_MAXIMO_RECEPCION // (1024 * 1024)),
        )

    emisor_id = _emisor_id()
    cliente = cliente or Rededoc()
    archivo.seek(0)
    respuesta = cliente.cargar_documentos_recibidos(
        emisor_id, archivo, nombre, EXTENSIONES_RECEPCION[extension],
    )
    if respuesta['error']:
        raise _error_rededoc(respuesta)
    return respuesta['datos'], respuesta['status']
