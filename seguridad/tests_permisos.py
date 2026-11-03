"""
Permisos dentro de un contenedor (`docs/permisos.md`).

La autorización vive en la membresía, en el público: `SegUsuarioCliente.is_superuser`,
`SegUsuarioClienteGrupo` (con `heredar_permisos`) y `SegUsuarioClientePermiso`.
`SegUsuario.has_perm()` la lee para el contenedor del header y `TienePermisoModelo`
la exige en cada petición.

Hace falta un contenedor real, con su schema migrado, porque las peticiones entran
con `X-Tenant`. Se crea una sola vez para el módulo (`setUpModule`), igual que en
`contenedor/tests_soporte.py`: cada `TestCase` revierte lo suyo.

Las peticiones llevan un JWT de verdad, así que en cada una la autenticación vuelve a
leer el usuario y sus permisos no quedan en caché de una petición a la otra.

Correr solo esto:

    python manage.py test seguridad.tests_permisos
"""

from datetime import timedelta

from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context
from rest_framework_simplejwt.tokens import RefreshToken
from tenant_users.permissions.models import UserTenantPermissions

from contenedor.models import (
    CtnCliente, CtnDominio, CtnPendiente, CtnPendienteTipo, CtnSuscripcion, CtnSuscripcionTipo,
)
from seguridad.models import (
    SegUsuario, SegUsuarioCliente, SegUsuarioClienteGrupo, SegUsuarioClientePermiso,
)

ESQUEMA = 'permisos_membresia'
RUTA_ITEM = '/general/item/'
RUTA_CONTACTO = '/general/contacto/'


def _permiso(codename):
    return Permission.objects.get(codename=codename, content_type__app_label='general')


class Escenario:
    cliente = None
    owner = None
    tipo = None


def _usuario(email):
    """Idempotente: con `--keepdb` el usuario sobrevive de una corrida a otra."""
    usuario, _ = SegUsuario.objects.get_or_create(
        email=email, defaults={'is_active': True, 'is_verified': True},
    )
    return usuario


def setUpModule():
    from general.signals import limpiar_caches

    limpiar_caches()
    with schema_context(get_public_schema_name()):
        Escenario.owner = _usuario('owner.permisos@ejemplo.com')
        Escenario.tipo, _ = CtnSuscripcionTipo.objects.get_or_create(
            id=95, defaults={'nombre': 'Plan permisos', 'precio': 0, 'suscripcion_categoria_id': 95},
        )
        cliente = CtnCliente(
            schema_name=ESQUEMA, nombre='Contenedor permisos', celular='+573000000000',
            correo='permisos@ejemplo.com', owner=Escenario.owner,
        )
        cliente.save(verbosity=0)
        CtnDominio.objects.create(tenant=cliente, domain='permisos.torio.test', is_primary=True)
        hoy = timezone.localdate()
        suscripcion = CtnSuscripcion.objects.create(
            cliente=cliente, usuario=Escenario.owner, suscripcion_tipo=Escenario.tipo,
            fecha_inicio=hoy - timedelta(days=1), fecha_fin=hoy + timedelta(days=30),
            frecuencia=CtnSuscripcion.FRECUENCIA_PRUEBA,
        )
        CtnCliente.objects.filter(pk=cliente.pk).update(suscripcion=suscripcion)
        cliente.refresh_from_db()
        cliente.add_user(Escenario.owner, propietario=True, is_superuser=True)
        Escenario.cliente = cliente


def tearDownModule():
    from general.signals import limpiar_caches

    with schema_context(get_public_schema_name()):
        if Escenario.cliente is not None:
            SegUsuarioCliente.objects.filter(cliente=Escenario.cliente).delete()
            CtnCliente.objects.filter(pk=Escenario.cliente.pk).update(suscripcion=None)
            CtnSuscripcion.objects.filter(cliente=Escenario.cliente).delete()
            CtnDominio.objects.filter(tenant=Escenario.cliente).delete()
            Escenario.cliente.delete(force_drop=True)
    limpiar_caches()


class PermisosBase(TestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(connection.set_schema_to_public)
        self.cliente = Escenario.cliente
        # Grupos propios de la prueba: los del producto los crea `sincronizar_grupos`,
        # que acá no corre, y así cada prueba sabe exactamente qué da cada grupo.
        self.grupo_item = Group.objects.create(name='prueba_item')
        self.grupo_item.permissions.set([_permiso('view_genitem'), _permiso('add_genitem')])
        self.grupo_contacto = Group.objects.create(name='prueba_contacto')
        self.grupo_contacto.permissions.set([_permiso('view_gencontacto')])

    # ---- armado ----

    def _miembro(self, email='miembro.permisos@ejemplo.com', grupos=(), permisos=(), **membresia):
        usuario = _usuario(email)
        fila = SegUsuarioCliente.objects.create(usuario=usuario, cliente=self.cliente, **membresia)
        for grupo, heredar in grupos:
            SegUsuarioClienteGrupo.objects.create(
                usuario_cliente=fila, grupo=grupo, heredar_permisos=heredar,
            )
        for codename in permisos:
            SegUsuarioClientePermiso.objects.create(usuario_cliente=fila, permiso=_permiso(codename))
        return usuario, fila

    @staticmethod
    def _headers(usuario, tenant=None):
        cabeceras = {'authorization': f'Bearer {RefreshToken.for_user(usuario).access_token}'}
        if tenant:
            cabeceras['x-tenant'] = tenant
        return {'headers': cabeceras}

    def _get(self, ruta, usuario, tenant=ESQUEMA, **kwargs):
        return self.client.get(ruta, **kwargs, **self._headers(usuario, tenant))

    def _post(self, ruta, datos, usuario, tenant=ESQUEMA):
        return self.client.post(
            ruta, datos, content_type='application/json', **self._headers(usuario, tenant),
        )

    def _put(self, ruta, datos, usuario):
        return self.client.put(ruta, datos, content_type='application/json', **self._headers(usuario))


# --------------------------------------------------------------------------- #
# La regla: superusuario, grupos que heredan y permisos personalizados se suman
# --------------------------------------------------------------------------- #

class ReglaDePermisosTests(PermisosBase):

    def test_sin_grupos_ni_permisos_no_puede_nada(self):
        usuario, _ = self._miembro()

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 403)

    def test_un_grupo_que_hereda_da_sus_permisos_y_solo_esos(self):
        usuario, _ = self._miembro(grupos=[(self.grupo_item, True)])

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 200)
        creado = self._post(RUTA_ITEM, {'nombre': 'Item permitido'}, usuario)
        self.assertEqual(creado.status_code, 201, creado.content)
        # El grupo no tiene `delete_genitem`.
        borrar = self.client.delete(f'{RUTA_ITEM}{creado.json()["id"]}/', **self._headers(usuario, ESQUEMA))
        self.assertEqual(borrar.status_code, 403)
        # Ni permisos de otros modelos.
        self.assertEqual(self._get(RUTA_CONTACTO, usuario).status_code, 403)

    def test_un_grupo_que_no_hereda_no_da_ningun_permiso(self):
        usuario, _ = self._miembro(grupos=[(self.grupo_item, False)])

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 403)

    def test_sin_heredar_vale_lo_personalizado(self):
        usuario, _ = self._miembro(grupos=[(self.grupo_item, False)], permisos=['view_genitem'])

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 200)
        # `add_genitem` está en el grupo, pero el grupo no hereda y no se personalizó.
        self.assertEqual(self._post(RUTA_ITEM, {'nombre': 'No'}, usuario).status_code, 403)

    def test_un_permiso_personalizado_fuera_de_sus_grupos_tambien_vale(self):
        usuario, _ = self._miembro(grupos=[(self.grupo_item, True)], permisos=['view_gencontacto'])

        self.assertEqual(self._get(RUTA_CONTACTO, usuario).status_code, 200)

    def test_los_permisos_se_suman_entre_grupos(self):
        """Un grupo sin heredar no le quita a otro que hereda el mismo permiso."""
        otro = Group.objects.create(name='prueba_item_ver')
        otro.permissions.set([_permiso('view_genitem')])
        usuario, _ = self._miembro(grupos=[(self.grupo_item, False), (otro, True)])

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 200)

    def test_el_superusuario_puede_todo_sin_grupos(self):
        usuario, _ = self._miembro(is_superuser=True)

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 200)
        self.assertEqual(self._get(RUTA_CONTACTO, usuario).status_code, 200)

    def test_userTenantPermissions_ya_no_autoriza(self):
        """Lo de la librería, aunque diga superusuario, no cuenta dentro del contenedor."""
        usuario, _ = self._miembro()
        with schema_context(ESQUEMA):
            UserTenantPermissions.objects.create(profile=usuario, is_superuser=True)

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 403)

    def test_lista_y_excel_exigen_solo_ver(self):
        usuario, _ = self._miembro(permisos=['view_genitem'])

        self.assertEqual(self._post(f'{RUTA_ITEM}lista/', {}, usuario).status_code, 200)
        self.assertEqual(self._post(f'{RUTA_ITEM}excel/', {}, usuario).status_code, 200)
        # Crear sigue exigiendo `add_`.
        self.assertEqual(self._post(RUTA_ITEM, {'nombre': 'No'}, usuario).status_code, 403)


class HasPermTests(PermisosBase):
    """`SegUsuario.has_perm` y compañía, sin pasar por una vista."""

    def test_calcula_una_vez_por_peticion(self):
        usuario, _ = self._miembro(grupos=[(self.grupo_item, True)])
        usuario = SegUsuario.objects.get(pk=usuario.pk)

        with tenant_context(self.cliente):
            with self.assertNumQueries(2):  # la membresía + los permisos
                self.assertTrue(usuario.has_perm('general.view_genitem'))
            with self.assertNumQueries(0):
                self.assertTrue(usuario.has_perm('general.add_genitem'))
                self.assertFalse(usuario.has_perm('general.delete_genitem'))
                self.assertTrue(usuario.has_perms(['general.view_genitem', 'general.add_genitem']))
                self.assertTrue(usuario.has_module_perms('general'))
                self.assertFalse(usuario.has_module_perms('contabilidad'))
                self.assertEqual(
                    usuario.get_all_permissions(), {'general.view_genitem', 'general.add_genitem'},
                )
                self.assertFalse(usuario.is_superuser)

    def test_sin_membresia_no_tiene_nada(self):
        usuario = SegUsuario.objects.get(pk=_usuario('ajeno.permisos@ejemplo.com').pk)

        with tenant_context(self.cliente):
            self.assertFalse(usuario.has_perm('general.view_genitem'))
            self.assertFalse(usuario.is_superuser)
            self.assertEqual(usuario.get_all_permissions(), set())

    def test_inactivo_no_tiene_nada(self):
        usuario, _ = self._miembro(is_superuser=True)
        SegUsuario.objects.filter(pk=usuario.pk).update(is_active=False)
        usuario = SegUsuario.objects.get(pk=usuario.pk)

        with tenant_context(self.cliente):
            self.assertFalse(usuario.has_perm('general.view_genitem'))
            self.assertFalse(usuario.has_module_perms('general'))

    def test_superusuario_tiene_todos_los_permisos(self):
        usuario, _ = self._miembro(is_superuser=True)
        usuario = SegUsuario.objects.get(pk=usuario.pk)

        with tenant_context(self.cliente):
            self.assertTrue(usuario.is_superuser)
            self.assertTrue(usuario.has_perm('contabilidad.delete_concuenta'))
            self.assertIn('general.view_genitem', usuario.get_all_permissions())

    def test_en_el_publico_se_comporta_como_la_libreria(self):
        """Ahí `is_staff`/`is_superuser` son de la plataforma, no de un contenedor."""
        usuario, _ = self._miembro(is_superuser=True)
        UserTenantPermissions.objects.create(profile=usuario, is_staff=True)
        usuario = SegUsuario.objects.get(pk=usuario.pk)

        self.assertTrue(usuario.is_staff)
        # Ser superusuario de un contenedor no lo hace superusuario de la plataforma.
        self.assertFalse(usuario.is_superuser)


# --------------------------------------------------------------------------- #
# GET/PUT /seguridad/usuario-cliente/<id>/grupo/ y /permiso/
# --------------------------------------------------------------------------- #

class EditarGruposTests(PermisosBase):

    def _ruta(self, fila):
        return f'/seguridad/usuario-cliente/{fila.id}/grupo/'

    def test_el_owner_los_reemplaza_con_ids_y_con_objetos(self):
        _, fila = self._miembro(grupos=[(self.grupo_contacto, True)])

        respuesta = self._put(self._ruta(fila), {'grupos': [
            self.grupo_item.id, {'grupo': self.grupo_contacto.id, 'heredar_permisos': False},
        ]}, Escenario.owner)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        por_grupo = {g['grupo_id']: g for g in respuesta.json()}
        self.assertEqual(
            (por_grupo[self.grupo_item.id]['activo'], por_grupo[self.grupo_item.id]['heredar_permisos']),
            (True, True),
        )
        self.assertEqual(por_grupo[self.grupo_contacto.id]['heredar_permisos'], False)
        self.assertEqual(
            dict(fila.grupos.values_list('grupo_id', 'heredar_permisos')),
            {self.grupo_item.id: True, self.grupo_contacto.id: False},
        )

    def test_una_lista_vacia_los_quita_y_el_get_muestra_los_inactivos(self):
        _, fila = self._miembro(grupos=[(self.grupo_item, True)])

        self.assertEqual(self._put(self._ruta(fila), {'grupos': []}, Escenario.owner).status_code, 200)

        self.assertFalse(fila.grupos.exists())
        [del_item] = [g for g in self._get(self._ruta(fila), Escenario.owner, tenant=None).json()
                      if g['grupo_id'] == self.grupo_item.id]
        self.assertEqual((del_item['activo'], del_item['heredar_permisos']), (False, None))

    def test_otro_miembro_no_los_edita(self):
        usuario, fila = self._miembro()

        respuesta = self._put(self._ruta(fila), {'grupos': [self.grupo_item.id]}, usuario)

        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(fila.grupos.exists())

    def test_a_soporte_no_se_le_editan(self):
        _, fila = self._miembro(soporte=True, is_superuser=True)

        self.assertEqual(self._put(self._ruta(fila), {'grupos': []}, Escenario.owner).status_code, 400)

    def test_datos_invalidos_400_con_detail(self):
        _, fila = self._miembro()
        casos = {
            'no es lista': {'grupos': 5},
            'falta': {},
            'bool': {'grupos': [True]},
            'heredar no bool': {'grupos': [{'grupo': self.grupo_item.id, 'heredar_permisos': 'si'}]},
            'repetido': {'grupos': [self.grupo_item.id, {'grupo': self.grupo_item.id}]},
            'inexistente': {'grupos': [999999]},
        }
        for caso, datos in casos.items():
            with self.subTest(caso):
                respuesta = self._put(self._ruta(fila), datos, Escenario.owner)
                self.assertEqual(respuesta.status_code, 400, respuesta.content)
                self.assertIsInstance(respuesta.json()['detail'], str)
        self.assertFalse(fila.grupos.exists())

    def test_una_membresia_de_otro_contenedor_no_se_encuentra(self):
        _, fila = self._miembro()
        ajeno = _usuario('ajeno.grupos@ejemplo.com')

        self.assertEqual(self._get(self._ruta(fila), ajeno, tenant=None).status_code, 404)
        self.assertEqual(self._put(self._ruta(fila), {'grupos': []}, ajeno).status_code, 404)

    def test_un_cambio_se_ve_en_la_peticion_siguiente(self):
        usuario, fila = self._miembro()
        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 403)

        self._put(self._ruta(fila), {'grupos': [self.grupo_item.id]}, Escenario.owner)

        self.assertEqual(self._get(RUTA_ITEM, usuario).status_code, 200)


class EditarPermisosTests(PermisosBase):

    def _ruta(self, fila):
        return f'/seguridad/usuario-cliente/{fila.id}/permiso/'

    def test_el_owner_los_reemplaza(self):
        _, fila = self._miembro(permisos=['view_gencontacto'])
        ver_item = _permiso('view_genitem')

        respuesta = self._put(self._ruta(fila), {'permisos': [ver_item.id]}, Escenario.owner)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        [unico] = respuesta.json()
        self.assertEqual(
            (unico['permiso_id'], unico['codename'], unico['app_label'], unico['modelo']),
            (ver_item.id, 'view_genitem', 'general', 'genitem'),
        )
        self.assertEqual(list(fila.permisos.values_list('permiso_id', flat=True)), [ver_item.id])

    def test_una_lista_vacia_los_quita(self):
        _, fila = self._miembro(permisos=['view_genitem'])

        self.assertEqual(self._put(self._ruta(fila), {'permisos': []}, Escenario.owner).json(), [])
        self.assertFalse(fila.permisos.exists())

    def test_otro_miembro_no_los_edita_pero_si_los_ve(self):
        usuario, fila = self._miembro(permisos=['view_genitem'])

        self.assertEqual(self._put(self._ruta(fila), {'permisos': []}, usuario).status_code, 403)
        self.assertEqual(len(self._get(self._ruta(fila), usuario, tenant=None).json()), 1)

    def test_a_soporte_no_se_le_editan(self):
        _, fila = self._miembro(soporte=True, is_superuser=True)

        self.assertEqual(self._put(self._ruta(fila), {'permisos': []}, Escenario.owner).status_code, 400)

    def test_datos_invalidos_400_con_detail(self):
        _, fila = self._miembro()
        for caso, datos in {
            'no es lista': {'permisos': 'view_genitem'},
            'bool': {'permisos': [False]},
            'inexistente': {'permisos': [999999]},
        }.items():
            with self.subTest(caso):
                respuesta = self._put(self._ruta(fila), datos, Escenario.owner)
                self.assertEqual(respuesta.status_code, 400, respuesta.content)
                self.assertIsInstance(respuesta.json()['detail'], str)


class MembresiaTests(PermisosBase):

    def test_salir_del_contenedor_borra_sus_grupos_y_permisos(self):
        _, fila = self._miembro(grupos=[(self.grupo_item, True)], permisos=['view_gencontacto'])

        respuesta = self.client.delete(
            f'/seguridad/usuario-cliente/{fila.id}/', **self._headers(Escenario.owner),
        )

        self.assertEqual(respuesta.status_code, 204, respuesta.content)
        self.assertFalse(SegUsuarioClienteGrupo.objects.filter(usuario_cliente_id=fila.id).exists())
        self.assertFalse(SegUsuarioClientePermiso.objects.filter(usuario_cliente_id=fila.id).exists())

    def test_lista_usuario_trae_superusuario_y_grupos(self):
        usuario, _ = self._miembro(grupos=[(self.grupo_item, False)])

        respuesta = self._get('/contenedor/cliente/lista-usuario/', usuario, tenant=None)
        del_owner = self._get('/contenedor/cliente/lista-usuario/', Escenario.owner, tenant=None)

        [propia] = respuesta.json()['results']
        self.assertEqual((propia['is_superuser'], propia['grupos']), (False, [self.grupo_item.id]))
        [la_del_owner] = del_owner.json()['results']
        self.assertIs(la_del_owner['is_superuser'], True)

    def test_add_user_guarda_superusuario_y_grupos_en_la_membresia(self):
        usuario = _usuario('nuevo.permisos@ejemplo.com')

        fila = self.cliente.add_user(usuario, grupos=[self.grupo_item])

        self.assertFalse(fila.is_superuser)
        self.assertEqual(
            list(fila.grupos.values_list('grupo_id', 'heredar_permisos')), [(self.grupo_item.id, True)],
        )
        with schema_context(ESQUEMA):
            permisos = UserTenantPermissions.objects.get(profile=usuario)
            self.assertFalse(permisos.is_superuser)
            self.assertFalse(permisos.groups.exists())

    def test_es_superusuario_lee_la_membresia_y_excluye_soporte(self):
        normal, _ = self._miembro('normal.permisos@ejemplo.com')
        soporte, _ = self._miembro('soporte.permisos@ejemplo.com', soporte=True, is_superuser=True)

        self.assertTrue(self.cliente.es_superusuario(Escenario.owner))
        self.assertFalse(self.cliente.es_superusuario(normal))
        self.assertFalse(self.cliente.es_superusuario(soporte))


# --------------------------------------------------------------------------- #
# GET /contenedor/pendiente/
# --------------------------------------------------------------------------- #

class PendientesVisiblesTests(PermisosBase):

    def setUp(self):
        super().setUp()
        self.tipo = CtnPendienteTipo.objects.create(id=901, nombre='Prueba', grupo=self.grupo_item)
        CtnPendiente.objects.create(
            cliente=self.cliente, pendiente_tipo=self.tipo, mensaje='Hay 2 cosas', cantidad=2,
        )

    def _pendientes(self, usuario, **params):
        return self.client.get('/contenedor/pendiente/', params, **self._headers(usuario))

    def test_lo_ve_quien_tiene_el_grupo_herede_o_no(self):
        for heredar in (True, False):
            with self.subTest(heredar=heredar):
                usuario, _ = self._miembro(f'grupo{heredar}.pend@ejemplo.com', grupos=[(self.grupo_item, heredar)])
                [pendiente] = self._pendientes(usuario).json()
                self.assertEqual(
                    (pendiente['cantidad'], pendiente['pendiente_tipo_grupo_id']), (2, self.grupo_item.id),
                )

    def test_lo_ve_el_superusuario(self):
        self.assertEqual(len(self._pendientes(Escenario.owner).json()), 1)

    def test_no_lo_ve_quien_no_tiene_el_grupo(self):
        usuario, _ = self._miembro(grupos=[(self.grupo_contacto, True)], permisos=['view_genitem'])

        self.assertEqual(self._pendientes(usuario).json(), [])

    def test_no_lo_ve_quien_no_es_miembro(self):
        self.assertEqual(self._pendientes(_usuario('ajeno.pend@ejemplo.com')).json(), [])

    def test_no_se_ven_los_de_un_contenedor_vencido(self):
        CtnSuscripcion.objects.filter(pk=self.cliente.suscripcion_id).update(
            fecha_fin=timezone.localdate() - timedelta(days=1),
        )

        self.assertEqual(self._pendientes(Escenario.owner).json(), [])

    def test_no_se_ven_los_de_cantidad_cero(self):
        CtnPendiente.objects.update(cantidad=0)

        self.assertEqual(self._pendientes(Escenario.owner).json(), [])

    def test_filtrar_por_cliente(self):
        self.assertEqual(len(self._pendientes(Escenario.owner, cliente=self.cliente.id).json()), 1)
        self.assertEqual(self._pendientes(Escenario.owner, cliente=999999).json(), [])
        invalido = self._pendientes(Escenario.owner, cliente='abc')
        self.assertEqual(invalido.status_code, 400)
        self.assertIsInstance(invalido.json()['detail'], str)

    def test_anonimo_401(self):
        self.assertEqual(self.client.get('/contenedor/pendiente/').status_code, 401)
