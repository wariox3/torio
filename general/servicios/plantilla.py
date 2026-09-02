"""
Carga de una plantilla de datos de arranque en el schema de un contenedor.

Una plantilla es **un archivo** de `general/plantillas/` con los datos de varios
modelos de tenant:

    {
      "nombre": "General",
      "descripcion": "...",
      "modelos": {
        "contabilidad.ConCuenta":   {"nombre": "Plan de cuentas", "datos": [ ... ]},
        "general.GenDocumentoTipo": {"modo": "actualizar", "datos": [ ... ]}
      }
    }

Cada bloque declara qué hace con sus filas:

- **`insertar`** (por defecto) — filas que la plantilla crea. Van en `bulk_create`.
- **`actualizar`** — filas que ya existen porque las sembró `cargar_datos_tenant`, y de
  las que la plantilla solo fija algunas columnas (típicamente la cuenta contable).

Los bloques de inserción van primero en el archivo: si uno falla, el recorrido se corta
antes de llegar a las actualizaciones.

**El orden de las claves de `modelos` es el orden de inserción.** `json.load` lo
conserva, y apoyarse en eso es seguro porque el fallo es ruidoso: si un bloque fuera
antes que aquel del que depende, la referencia natural no resuelve y todo se deshace.

Las referencias a otras filas se escriben de dos formas:

- **escalar** → ya es la PK. Para catálogo estable que sembró `cargar_datos_tenant`
  (`"cuenta_clase": 1`).
- **objeto** → es una búsqueda. Para lo que crea la propia plantilla
  (`"cuenta": {"codigo": "233595"}`), y así no hay números mágicos entre bloques.

Esto no reusa `cargar_datos_tenant`: aquel carga los catálogos en todos los tenants,
con otro formato y semántica idempotente. Acá la carga es de una plantilla concreta
en un schema concreto, y es todo o nada.
"""

import json
from collections import defaultdict
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, FieldError
from django.db import DatabaseError, connection, transaction
from django_tenants.utils import schema_context

RUTA = Path(settings.BASE_DIR) / 'general' / 'plantillas'

# Qué hace un bloque con sus filas. Por defecto inserta; los bloques que ajustan
# catálogo ya sembrado por `cargar_datos_tenant` declaran `"modo": "actualizar"`.
MODO_INSERTAR = 'insertar'
MODO_ACTUALIZAR = 'actualizar'
MODOS = (MODO_INSERTAR, MODO_ACTUALIZAR)

# Mismo criterio que `cargar_datos_tenant`: 500 filas por sentencia deja margen de
# sobra frente al tope de 65.535 parámetros por consulta de Postgres.
TAMANO_LOTE = 500


class PlantillaError(Exception):
    """Plantilla inexistente, mal formada o que no se puede aplicar."""


def leer(archivo):
    """
    Contenido de una plantilla por nombre de archivo (`01_general.json`).

    El nombre acaba viniendo de fuera, así que la ruta se resuelve y se comprueba
    que caiga directamente en `general/plantillas/`: sin esto, un `../` alcanzaría
    cualquier JSON del proyecto.
    """
    ruta = (RUTA / archivo).resolve()
    if ruta.parent != RUTA.resolve() or ruta.suffix != '.json' or not ruta.is_file():
        raise PlantillaError(f'No existe la plantilla "{archivo}".')
    try:
        return json.loads(ruta.read_text(encoding='utf-8'))
    except json.JSONDecodeError as error:
        raise PlantillaError(f'{archivo}: JSON inválido ({error}).')


def aplicar(schema_name, archivo):
    """
    Inserta la plantilla en el schema indicado. Todo o nada.

    **Si una inserción falla se interrumpe el proceso y no queda nada**: la excepción
    sale de la transacción, que deshace lo insertado hasta ese punto —incluidos los
    bloques anteriores—, y el llamador recibe un `PlantillaError`. Una plantilla a
    medias es peor que ninguna: sus filas se referencian entre sí, así que dejarla
    incompleta produce FKs colgando.

    Los bloques se recorren en el orden del archivo, con los de inserción primero: si
    uno falla, las actualizaciones ni se ejecutan. La inserción va sin
    `ignore_conflicts` a propósito —una fila que ya exista ahí es un error y tiene que
    reventar, no omitirse en silencio—; para ajustar catálogo ya sembrado está el modo
    `actualizar`.

    Corre **después** de `cargar_datos_tenant --inicial`: las filas apuntan por FK a
    los catálogos y a los datos semilla.

    Devuelve {etiqueta del modelo: filas insertadas}.
    """
    contenido = leer(archivo)
    modelos = contenido.get('modelos')
    if not isinstance(modelos, dict):
        raise PlantillaError(f'{archivo}: falta el objeto "modelos".')

    resumen = {}
    with schema_context(schema_name), transaction.atomic():
        for etiqueta, bloque in modelos.items():
            modelo = _modelo(etiqueta, archivo)
            modo = bloque.get('modo', MODO_INSERTAR)
            if modo not in MODOS:
                raise PlantillaError(
                    f'{etiqueta}: modo "{modo}" desconocido (esperado: {", ".join(MODOS)}).'
                )
            filas = bloque.get('datos') or []
            if modo == MODO_INSERTAR:
                _insertar(modelo, filas, etiqueta)
            else:
                _actualizar(modelo, filas, etiqueta)
            resumen[etiqueta] = len(filas)
    return resumen


def _insertar(modelo, filas, etiqueta):
    objetos = [modelo(**_atributos(modelo, fila, etiqueta)) for fila in filas]
    try:
        modelo.objects.bulk_create(objetos, batch_size=TAMANO_LOTE)
    except DatabaseError as error:
        raise PlantillaError(f'{etiqueta}: {error}') from error
    # Las filas traen id explícito y la secuencia no avanza con esos INSERT: sin esto,
    # el siguiente insert del ORM reutiliza un id ya ocupado.
    _resetear_secuencia(modelo)


def _actualizar(modelo, filas, etiqueta):
    """
    Ajusta filas que ya existen: las que sembró `cargar_datos_tenant` y de las que la
    plantilla solo fija algunas columnas.

    Dos cuidados que no son opcionales:

    - **Se comprueba antes que los pks existan.** `bulk_update` sobre un id inexistente
      no falla: simplemente no actualiza nada. Si el catálogo cambiara de ids, la
      plantilla se aplicaría "bien" sin haber hecho nada.
    - **Las filas se agrupan por conjunto de claves.** Dentro de un mismo bloque no
      todas traen las mismas columnas (6 tipos de documento fijan `cuenta_cobrar` y 8
      `cuenta_pagar`; 16 provisiones traen `cuenta_credito` y 24 no). Con la unión como
      `fields`, una fila que no trae una columna la sobreescribiría con el default del
      modelo —borrando en silencio lo que tenía el catálogo—, así que cada grupo se
      actualiza con exactamente sus columnas.
    """
    pk_clave = modelo._meta.pk.name
    sin_pk = [fila for fila in filas if pk_clave not in fila]
    if sin_pk:
        raise PlantillaError(f'{etiqueta}: hay filas a actualizar sin "{pk_clave}".')

    pks = [fila[pk_clave] for fila in filas]
    existentes = set(modelo.objects.filter(pk__in=pks).values_list('pk', flat=True))
    faltan = [pk for pk in pks if pk not in existentes]
    if faltan:
        raise PlantillaError(
            f'{etiqueta}: la plantilla actualiza filas que no existen: {faltan}.'
        )

    grupos = defaultdict(list)
    for fila in filas:
        grupos[frozenset(fila) - {pk_clave}].append(fila)

    for claves, grupo in grupos.items():
        if not claves:
            continue  # fila que solo trae el id: no hay nada que actualizar
        objetos = [modelo(**_atributos(modelo, fila, etiqueta)) for fila in grupo]
        # `bulk_update` espera nombres de campo (`cuenta_pagar`), no columnas.
        campos = sorted(_campo(modelo, clave, etiqueta).name for clave in claves)
        try:
            modelo.objects.bulk_update(objetos, campos, batch_size=TAMANO_LOTE)
        except DatabaseError as error:
            raise PlantillaError(f'{etiqueta}: {error}') from error


# ── Traducción de una fila del JSON a atributos del modelo ──────────────────

def _modelo(etiqueta, archivo):
    try:
        return apps.get_model(etiqueta)
    except (LookupError, ValueError):
        raise PlantillaError(f'{archivo}: no existe el modelo "{etiqueta}".')


def _campo(modelo, clave, etiqueta):
    try:
        campo = modelo._meta.get_field(clave)
    except FieldDoesNotExist:
        raise PlantillaError(f'{etiqueta}: el campo "{clave}" no existe en el modelo.')
    if not campo.concrete:
        raise PlantillaError(f'{etiqueta}: "{clave}" no es una columna del modelo.')
    return campo


def _atributos(modelo, fila, etiqueta):
    """
    {attname: valor} listo para el constructor del modelo.

    El JSON nombra las FK por el campo (`cuenta_clase`), no por la columna
    (`cuenta_clase_id`); la traducción se hace acá, en un solo sitio.
    """
    return {
        campo.attname: _valor(campo, valor, etiqueta, clave)
        for clave, valor in fila.items()
        for campo in (_campo(modelo, clave, etiqueta),)
    }


def _valor(campo, valor, etiqueta, clave):
    """Un escalar se toma tal cual; un objeto sobre una FK se busca en la base."""
    if not campo.is_relation or not isinstance(valor, dict):
        return valor

    destino = campo.related_model
    try:
        return destino.objects.get(**valor).pk
    except destino.DoesNotExist:
        raise PlantillaError(
            f'{etiqueta}.{clave}: ningún {destino._meta.label} cumple {valor}.'
        )
    except destino.MultipleObjectsReturned:
        raise PlantillaError(
            f'{etiqueta}.{clave}: {valor} identifica a más de un {destino._meta.label}.'
        )
    except (FieldError, TypeError, ValueError) as error:
        raise PlantillaError(f'{etiqueta}.{clave}: búsqueda inválida {valor} ({error}).')


def _resetear_secuencia(modelo):
    """
    Deja la secuencia de la PK por encima del mayor id insertado.

    Duplica `Command._resetear_secuencia` de `cargar_datos_tenant`, que lo necesita
    por lo mismo. Se puede unificar en `utilidades/`, pero eso toca el comando y no
    es parte de este cambio.
    """
    tabla = modelo._meta.db_table
    pk_col = modelo._meta.pk.column
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_get_serial_sequence(%s, %s)', [tabla, pk_col])
        secuencia = cursor.fetchone()[0]
        if not secuencia:
            # PK manual sin secuencia (p.ej. BigIntegerField); nada que ajustar.
            return
        cursor.execute(
            f"SELECT setval('{secuencia}', COALESCE(MAX({pk_col}), 1)) FROM {tabla}"
        )
