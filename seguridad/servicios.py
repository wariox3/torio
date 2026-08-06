"""
Aplicación de la declaración de grupos de `seguridad.grupos` sobre la base.

Los `Group` y sus permisos viven en el schema público. Qué grupos tiene un
usuario dentro de un contenedor concreto se guarda en su `UserTenantPermissions`,
en el schema de ese tenant, y lo escribe `CtnCliente.add_user`.
"""

from django.contrib.auth.models import Group, Permission
from django.db import connection
from django_tenants.utils import get_public_schema_name, schema_context

from seguridad.grupos import GRUPOS


def sincronizar_grupos():
    """
    Crea los grupos declarados con su id fijo y reemplaza sus permisos por los de
    la declaración. Idempotente.

    No borra los grupos ausentes de la declaración: se asume que pueden crearse
    y administrarse también desde fuera.

    Devuelve {nombre_grupo: cantidad de permisos asignados}.
    """
    resumen = {}
    with schema_context(get_public_schema_name()):
        for pk, (nombre, matriz) in GRUPOS.items():
            grupo, _ = Group.objects.update_or_create(id=pk, defaults={'name': nombre})
            permisos = permisos_declarados(matriz)
            grupo.permissions.set(permisos)
            resumen[nombre] = len(permisos)
        _resetear_secuencia()
    return resumen


def _resetear_secuencia():
    """
    Avanza la secuencia de `auth_group` tras insertar ids explícitos, o el
    próximo grupo que cree Django colisionaría. Mismo cuidado que toma
    `cargar_datos_tenant` con los fixtures de id manual.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence('auth_group', 'id'), "
            'COALESCE((SELECT MAX(id) FROM auth_group), 1))'
        )


def permisos_declarados(matriz):
    """
    Resuelve una matriz {objetivo: acciones} a una lista de `Permission`.

    Cada clave es `app_label` (toda la app) o `app_label.modelo` (un modelo).
    """
    permisos = []
    for objetivo, acciones in matriz.items():
        app_label, _, modelo = objetivo.partition('.')
        consulta = Permission.objects.filter(content_type__app_label=app_label)
        if modelo:
            consulta = consulta.filter(content_type__model=modelo)
        prefijos = tuple(f'{accion}_' for accion in acciones)
        permisos += [p for p in consulta if p.codename.startswith(prefijos)]
    return permisos
