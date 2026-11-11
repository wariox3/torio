# Permisos dentro de un contenedor

Estado: **implementado**. Modelos `seguridad/models/usuario_cliente.py` (`propietario`, `administrador`, `soporte`),
`usuario_cliente_grupo.py` y `usuario_cliente_permiso.py` (migraciones `seguridad/0032` y
`0033`). El cálculo está en `seguridad/models/usuario.py` (`SegUsuario.has_perm` y
compañía), la regla por petición en `seguridad/permissions.py` (`TienePermisoModelo`) y los
endpoints en `seguridad/views/usuario_cliente.py`.

## 1. Por qué

django-tenant-users guarda los permisos de cada usuario **dentro del schema de cada
contenedor**: `UserTenantPermissions`, con `is_superuser`, `groups` y `user_permissions`.
Eso obliga a entrar a cada schema para saber qué puede hacer un usuario en cada uno de sus
contenedores. Y hay cosas que se calculan desde el público, sin `X-Tenant`, para todos los
contenedores del usuario a la vez:

- `lista-usuario`: el menú de cada contenedor.
- `GET /contenedor/pendiente/`: qué pendientes ve el usuario al iniciar sesión.

Por eso la autorización se movió a la **membresía** (`SegUsuarioCliente`), que ya vive en el
público y ya representa «este usuario en este contenedor».

## 2. Dónde vive cada cosa

```
public.seg_usuario_cliente                (usuario + contenedor)
 ├─ propietario, administrador o soporte → todos los permisos en ese contenedor
 ├─ seg_usuario_cliente_grupo             → auth_group (+ heredar_permisos)
 │                                          └─ auth_group_permissions → auth_permission
 └─ seg_usuario_cliente_permiso           → auth_permission (permisos personalizados)
```

| Tabla | Qué es |
|---|---|
| `auth_permission` | Catálogo de Django: un permiso por modelo y acción (`view_`, `add_`, `change_`, `delete_`). Lo llena `migrate`. |
| `auth_group` / `auth_group_permissions` | Los 8 grupos del producto con ids fijos (`seguridad/grupos.py`). Sus permisos los aplica `sincronizar_grupos`, que corre `cargar_geodata`. |
| `seg_usuario_cliente.propietario` | El dueño. **Tiene todo**: `has_perm`, pendientes y el `is_superuser` que calcula la API lo leen como `propietario OR administrador OR soporte`, y `es_superusuario` como `propietario OR administrador`. Solo él transfiere la propiedad y elimina el contenedor (`es_propietario`). |
| `seg_usuario_cliente.administrador` | Lo marca el dueño o otro administrador (`POST /seguridad/usuario-cliente/<id>/administrador/`), nunca sobre el propietario ni el soporte. **Tiene todo lo del dueño** —permisos (`has_perm`, pendientes, `is_superuser` de la API) y `es_superusuario`: editar el contenedor y su imagen, invitar, grupos, permisos, administradores, sacar miembros, reintentar la creación— **salvo transferir la propiedad y eliminar el contenedor**. Al transferir, el dueño anterior queda administrador. |
| `seg_usuario_cliente.soporte` | Staff de la plataforma dando soporte. **También basta para tener todos los permisos** (`has_perm`, pendientes, `is_superuser` de la API), pero no cuenta en `es_superusuario`: no modifica ni elimina el contenedor. |
| `seg_usuario_cliente_grupo` | Grupos del miembro. `heredar_permisos` (por defecto `true`) decide si el grupo da sus permisos. |
| `seg_usuario_cliente_permiso` | Permisos sueltos del miembro: **cualquier** permiso, esté o no en sus grupos. |

`UserTenantPermissions` se sigue creando en cada schema (`add_user`, `crear_contenedor`),
**vacío**, solo porque la librería lo espera. Nada lo lee para autorizar dentro de un
contenedor.

## 3. La regla

```
superusuario en el contenedor            → todos los permisos
si no, un permiso se concede si:
    algún grupo suyo con heredar_permisos = true lo contiene
    o es uno de sus permisos personalizados
sin membresía en el contenedor           → ningún permiso
usuario inactivo                         → ningún permiso
```

- Los permisos **se suman, nunca se restan**. No hay permisos negativos.
- Un grupo con `heredar_permisos = false` no da ningún permiso. Sigue sirviendo para el
  menú y para los pendientes del módulo, y lo que el miembro puede hacer sale de sus
  permisos personalizados.
- **Modelos compartidos.** Los permisos de Django son por modelo, y 7 modelos están en
  varios grupos (`GenDocumento` en los 8; `GenContacto`, `GenItem`, `InvAlmacen`,
  `GenFormaPago`, `GenCuentaBanco`, `GenResolucion` en varios). Quitar un permiso de un
  modelo compartido solo funciona si **ningún** otro grupo del miembro que herede lo
  incluye.
- El permiso es por modelo, no por tipo de documento: `general.add_gendocumento` permite
  crear cualquier documento, sea factura, compra o nómina.

### En el público

Sin `X-Tenant`, `SegUsuario` se comporta como en la librería: `is_staff` e `is_superuser`
salen del `UserTenantPermissions` del schema público. Son los de **la plataforma**, no los
de un contenedor: los usa `EsStaff` (panel de administración y soporte) y los crea
`createsuperuser`.

## 4. Cómo se calcula

`SegUsuario._permisos_contenedor` (un `tenant_cached_property`) hace, por petición y por
schema:

1. Una consulta a `seg_usuario_cliente` por `(usuario_id, cliente_id)` para obtener la
   membresía, su `propietario`, su `administrador` y su `soporte`.
2. Si no tiene ninguna de las tres, una consulta con `UNION`: los permisos de sus grupos con
   `heredar_permisos` y sus permisos personalizados.

Todo va por índice (`(usuario_id, cliente_id)`, `(usuario_cliente_id, grupo_id)`,
`(usuario_cliente_id, permiso_id)`). La única tabla que se recorre completa es
`auth_group_permissions`, que tiene unas 200 filas fijas del producto. Medido en desarrollo:
0,28 ms. El tamaño no crece con la cantidad de usuarios.

El resultado se guarda en la instancia del usuario. En una petición real la instancia es
nueva cada vez (la autenticación JWT la busca), así que un cambio de grupos se ve en la
petición siguiente. **En los tests** con `APIClient.force_authenticate(usuario)` la misma
instancia se reutiliza entre peticiones: después de cambiar grupos o permisos hay que
volver a leer el usuario (`SegUsuario.objects.get(pk=...)`).

## 5. Qué exige cada vista

`TienePermisoModelo` (en `seguridad/permissions.py`) exige, en este orden:

1. Ser miembro del contenedor (`EsMiembroDelTenant`).
2. Suscripción vigente (`SuscripcionVigente`).
3. Si es superusuario en el contenedor, pasa.
4. Si no, el permiso de Django del modelo del viewset según el método HTTP:

| Método | Permiso |
|---|---|
| `GET`, `HEAD`, `OPTIONS` | `view_<modelo>` |
| `POST` | `add_<modelo>` |
| `PUT`, `PATCH` | `change_<modelo>` |
| `DELETE` | `delete_<modelo>` |

Excepción: las acciones de `ACCIONES_LECTURA` (`lista` de `FiltrosDinamicosMixin` y `excel`
de `ExportarExcelMixin`) van por `POST` porque el cuerpo lleva los filtros, pero exigen
`view_<modelo>`.

Las acciones de `ACCIONES_SIN_PERMISO_MODELO` (`seleccionar`) no exigen ningún permiso
sobre el modelo, solo membresía y suscripción vigente: llenan los selectores de otros
formularios, y quien no administra el modelo igual necesita elegir un registro.

Las vistas que se quedan con los permisos por defecto (`EsMiembroDelTenant` +
`SuscripcionVigente`) **no miran permisos**: cualquier miembro del contenedor las usa. Ver
la sección 8.

`GET /general/modelo/...` devuelve `ver`, `crear`, `editar` y `eliminar` con `has_perm()`:
es lo que usa el front para mostrar u ocultar botones.

## 6. Cómo se asignan

| Momento | Qué queda |
|---|---|
| Crear contenedor (`POST /contenedor/cliente/`) | El dueño: `propietario` |
| Marcar administrador (`POST /seguridad/usuario-cliente/<id>/administrador/`) | `administrador` |
| Transferir (`POST /contenedor/cliente/<id>/transferir/`, con clave) | El nuevo: `propietario`; el anterior: `administrador`. Se borran sus invitaciones pendientes |
| Soporte (`POST /contenedor/cliente/<id>/soporte/`) | `soporte` |
| Aceptar invitación | Los `grupo_ids` de la invitación (opcional), con `heredar_permisos = true` |
| `POST`/`DELETE /seguridad/usuario-cliente-grupo/` | Agrega o quita un grupo, con su `heredar_permisos` |
| `POST`/`DELETE /seguridad/usuario-cliente-permiso/` | Agrega o quita un permiso personalizado |
| Salir del contenedor (`DELETE /seguridad/usuario-cliente/<id>/`) | Se borra la membresía con sus grupos y permisos (CASCADE) |

El `POST` y el `DELETE` de grupos y de permisos los hacen el **dueño** o un **administrador**
del contenedor (`es_superusuario`); otro miembro recibe 403. A una membresía de soporte no se le editan (400). El `GET` lo
puede hacer cualquier miembro del contenedor.

### `/seguridad/usuario-cliente-grupo/` y `/seguridad/usuario-cliente-permiso/`

Los grupos y los permisos personalizados de un miembro, gestionados de a uno. Los
catálogos para los selectores son `GET /seguridad/grupo/` y `GET /seguridad/permiso/`.

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `?usuario_cliente_id=<id>` (opcional, también `grupo_id` / `permiso_id`) | Lista paginada |
| `POST` | `/lista/` | Filtros dinámicos sobre `id`, `usuario_cliente_id` y `grupo_id` (+ `heredar_permisos`) o `permiso_id` |
| `POST` | `/` | Agrega uno (201) |
| `DELETE` | `/<id>/` | Quita uno (204) |

```json
POST /seguridad/usuario-cliente-grupo/   { "usuario_cliente": 5, "grupo": 7, "heredar_permisos": false }
POST /seguridad/usuario-cliente-permiso/ { "usuario_cliente": 5, "permiso": 101 }
```

`heredar_permisos` es opcional (`true` por defecto). Cada fila de grupo trae `id`,
`usuario_cliente`, `grupo`, `grupo_name` y `heredar_permisos`; cada fila de permiso, `id`,
`usuario_cliente`, `permiso`, `permiso_codename`, `permiso_name`,
`permiso_content_type_app_label` y `permiso_content_type_model`.

No hay `PUT`: para cambiar `heredar_permisos` se quita el grupo y se vuelve a agregar. Las
validaciones están en el serializer y responden 400 con `detail`: membresía inexistente o
de un contenedor al que no se pertenece, membresía de soporte, grupo o permiso
inexistente, permiso de una app no asignable y repetido. Que solo el owner o un administrador
modifique se revisa en la vista (403). Las filas de un contenedor al que no se pertenece no se listan
y su `DELETE` da 404.

## 7. Menú y pendientes

- `lista-usuario` y `usuario-cliente` devuelven, por membresía, `is_superuser` (calculado:
  `true` para el propietario, el administrador y el soporte; no es una columna) y `grupos` (ids). El front muestra el módulo de cada grupo del producto, y todos si es
  superusuario.
- `CtnPendienteTipo.grupo` dice de qué módulo es cada pendiente. Un pendiente se ve si la
  membresía es propietaria, administradora o de soporte, o tiene ese grupo, herede o no (`docs/pendientes.md`).

## 8. Límites conocidos

- **Vistas sin permiso de modelo.** Hay viewsets de los módulos que solo exigen ser
  miembro, entre ellos algunos que escriben (configuración de la empresa, facturación
  electrónica, detalles y pagos de documentos, precios, conceptos y cuentas de nómina).
  Mientras todos los miembros eran superusuarios no se notaba. Ver el análisis de
  seguridad.
- **Acciones de lectura por `POST` en los módulos** (`imprimir`, `pdf`, `totales`,
  `pendiente`…) exigen `add_<modelo>`. Solo `lista` y `excel` están en
  `ACCIONES_LECTURA`.
- **Sin permisos por tipo de documento.** Ver la regla en la sección 3.

## 9. Despliegue de este cambio

Las migraciones 0032/0033 solo crean estructura. La 0035 (2026-11-11) quita
`seg_usuario_cliente.is_superuser`: antes pasa a `administrador` toda membresía que lo tuviera
sin ser propietaria ni de soporte (las que se marcaron con un `UPDATE` manual), así que nadie
pierde acceso y no hay que correr nada a mano.
